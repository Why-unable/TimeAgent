"""Run deterministic and real-Agent planning evaluations on isolated fixture users."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from math import ceil
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError, CommandParser
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.context import RuntimeContext
from apps.agents.model import build_chat_model
from apps.events.services import CreateEventCommand, EventService
from apps.observability.models import LLMCallAudit
from apps.planning.models import SchedulePlan
from apps.planning.schemas import DailyAvailabilityWindow
from apps.planning.services import PlanningService
from apps.preferences.services import UserPreferenceService
from apps.tasks.models import TaskStatus
from apps.tasks.services import CreateTaskCommand, TaskService
from apps.time_memory.semantic_schemas import MemoryProposalPayload
from apps.time_memory.semantic_services import SemanticMemoryService


class Command(BaseCommand):
    help = "Compare the deterministic planner with the real Time Steward harness."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dataset", type=Path, help="Planning scenario JSON fixture.")
        parser.add_argument("--case", action="append", dest="case_ids")
        parser.add_argument("--include-holdout", action="store_true")
        parser.add_argument("--repeats", type=int, default=1)
        parser.add_argument("--variant", choices=("baseline", "agent", "both"), default="both")
        parser.add_argument(
            "--model",
            help="Configured model alias; defaults to agent.default_model.",
        )
        parser.add_argument("--output", type=Path, help="Output report path.")

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        repeats = int(options["repeats"])
        if repeats < 1 or repeats > 5:
            raise CommandError("--repeats must be between 1 and 5")

        dataset_path = options.get("dataset") or self._default_dataset_path()
        scenarios = self._load_scenarios(dataset_path)
        requested = set(options.get("case_ids") or [])
        if requested:
            known = {str(item["id"]) for item in scenarios}
            unknown = requested - known
            if unknown:
                raise CommandError(f"Unknown scenario id(s): {', '.join(sorted(unknown))}")
            scenarios = [item for item in scenarios if str(item["id"]) in requested]
        if not options["include_holdout"]:
            scenarios = [item for item in scenarios if item.get("split") != "holdout"]
        if not scenarios:
            raise CommandError("No planning scenarios selected")

        variant = str(options["variant"])
        variants = ("baseline", "agent") if variant == "both" else (variant,)
        agent = None
        if "agent" in variants:
            model_alias = options.get("model")
            from langgraph.store.memory import InMemoryStore

            agent = (
                build_time_steward_agent(
                    checkpointer=InMemorySaver(),
                    store=InMemoryStore(),
                )
                if model_alias is None
                else build_time_steward_agent(
                    model=build_chat_model(model_alias),
                    checkpointer=InMemorySaver(),
                    store=InMemoryStore(),
                )
            )

        results: list[dict[str, Any]] = []
        audit_request_ids: list[str] = []
        try:
            for scenario in scenarios:
                for repeat_index in range(1, repeats + 1):
                    for selected_variant in variants:
                        started = perf_counter()
                        user, task_map = self._seed_scenario(scenario)
                        request_id = str(uuid4())
                        audit_request_ids.append(request_id)
                        memory_context = {
                            "semantic_memory_count": 0,
                            "behavior_profile_available": False,
                        }
                        pending_approval_tool_names: list[str] = []
                        try:
                            if selected_variant == "baseline":
                                raw_expectations = scenario.get("expectations", {})
                                expectations_for_baseline = (
                                    raw_expectations if isinstance(raw_expectations, dict) else {}
                                )
                                hard_labels = expectations_for_baseline.get("hard", [])
                                baseline_daily_limit = (
                                    expectations_for_baseline.get("max_daily_minutes")
                                    if "max_daily_minutes" in hard_labels
                                    else None
                                )
                                baseline_daily_windows = [
                                    DailyAvailabilityWindow.model_validate(window)
                                    for window in expectations_for_baseline.get(
                                        "daily_availability_windows", []
                                    )
                                ]
                                active_task_ids = [
                                    task.pk
                                    for task in task_map.values()
                                    if task.status
                                    not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
                                ]
                                plans = [
                                    PlanningService.propose_schedule_plan(
                                        user=user,
                                        task_ids=active_task_ids,
                                        range_start=self._datetime(scenario["range_start"]),
                                        range_end=self._datetime(scenario["range_end"]),
                                        strategy="plan_tasks_only",
                                        max_daily_minutes=baseline_daily_limit,
                                        daily_worktime_overrides=baseline_daily_windows,
                                        now=self._datetime(scenario["anchor_at"]),
                                    )
                                ]
                                tool_trace: list[dict[str, Any]] = []
                                final_response = ""
                            else:
                                assert agent is not None
                                (
                                    final_response,
                                    tool_trace,
                                    memory_context,
                                    pending_approval_tool_names,
                                ) = self._invoke_agent(
                                    agent=agent,
                                    user=user,
                                    scenario=scenario,
                                    request_id=request_id,
                                    task_map=task_map,
                                )
                                plans = list(
                                    SchedulePlan.objects.filter(user=user).order_by(
                                        "created_at", "id"
                                    )
                                )

                            metrics = [
                                self._plan_metrics(
                                    scenario=scenario,
                                    plan=plan,
                                    task_map=task_map,
                                    final_response=final_response,
                                )
                                for plan in plans
                            ]
                            usage = self._usage_for_request(request_id)
                            hard_failures = list(metrics[-1]["hard_violations"]) if metrics else []
                            candidate_time_violations = (
                                self._candidate_time_violations(
                                    final_response,
                                    scenario=scenario,
                                    tool_trace=tool_trace,
                                )
                                if selected_variant == "agent"
                                else []
                            )
                            hard_failures.extend(candidate_time_violations)
                            replan_metrics = (
                                self._replan_candidate_metrics(
                                    response=final_response,
                                    scenario=scenario,
                                    tool_trace=tool_trace,
                                )
                                if selected_variant == "agent"
                                else {}
                            )
                            failed_tools = [
                                call["name"] for call in tool_trace if call.get("status") == "error"
                            ]
                            recovered_tool_errors, unresolved_tool_errors = (
                                self._classify_tool_errors(tool_trace)
                            )
                            agent_requested_clarification = self._asks_planning_clarification(
                                final_response
                            )
                            approval_interrupt_pending = bool(pending_approval_tool_names)
                            expectations = scenario.get("expectations", {})
                            max_candidate_plans = (
                                expectations.get("max_candidate_plans", 1)
                                if isinstance(expectations, dict)
                                else 1
                            )
                            plan_count_limit_passed = selected_variant != "agent" or (
                                self._plan_count_limit_passed(
                                    candidate_count=len(plans),
                                    maximum=max_candidate_plans,
                                )
                            )
                            clarification_expectation = (
                                expectations.get("ask_planning_clarification")
                                if isinstance(expectations, dict)
                                else None
                            )
                            if selected_variant == "baseline":
                                workflow_succeeded = (
                                    bool(plans) and clarification_expectation is not True
                                )
                            elif clarification_expectation is True:
                                workflow_succeeded = agent_requested_clarification
                            elif (
                                isinstance(expectations, dict)
                                and expectations.get("approval_required") is True
                            ):
                                workflow_succeeded = approval_interrupt_pending
                            else:
                                workflow_succeeded = bool(plans)
                            forbidden_tool_names = {
                                "mutate_events",
                                "create_recurring_event",
                                "reschedule_task",
                                "apply_schedule_plan",
                                "apply_local_replan",
                                "create_event",
                                "create_event_batch",
                                "create_task",
                                "create_task_batch",
                                "update_task",
                                "complete_task",
                                "cancel_task",
                            }
                            if (
                                isinstance(expectations, dict)
                                and expectations.get("no_schedule_write_before_answer") is True
                            ):
                                forbidden_tool_names.update(
                                    {"propose_schedule_plan", "compare_schedule_plans"}
                                )
                            forbidden_tools_used = [
                                str(call["name"])
                                for call in tool_trace
                                if call.get("name") in forbidden_tool_names
                                and not (
                                    call.get("status") == "unknown"
                                    and str(call.get("name")) in pending_approval_tool_names
                                )
                            ]
                            if (
                                selected_variant == "baseline"
                                and isinstance(expectations, dict)
                                and expectations.get("no_schedule_write_before_answer") is True
                                and plans
                            ):
                                forbidden_tools_used.append(
                                    "baseline_schedule_created_before_clarification"
                                )
                            clarification_question_count = (
                                self._clarifying_question_count(final_response)
                                if selected_variant == "agent"
                                else None
                            )
                            max_questions = (
                                expectations.get("max_clarifying_questions")
                                if isinstance(expectations, dict)
                                else None
                            )
                            question_limit_passed = (
                                selected_variant != "agent"
                                or not isinstance(max_questions, int)
                                or clarification_question_count is not None
                                and clarification_question_count <= max_questions
                            )
                            clarification_targets_met = (
                                self._clarification_targets_met(
                                    scenario,
                                    final_response,
                                    tool_trace=tool_trace,
                                )
                                if selected_variant == "agent"
                                else None
                            )
                            result = {
                                "scenario_id": scenario["id"],
                                "split": scenario.get("split", "regression"),
                                "variant": selected_variant,
                                "repeat": repeat_index,
                                "passed": (
                                    not hard_failures
                                    and not unresolved_tool_errors
                                    and not forbidden_tools_used
                                    and workflow_succeeded
                                    and question_limit_passed
                                    and plan_count_limit_passed
                                    and clarification_targets_met is not False
                                    and replan_metrics.get("passed", True)
                                ),
                                "duration_seconds": round(perf_counter() - started, 4),
                                "task_facts": self._task_facts(scenario),
                                "event_facts": scenario.get("events", []),
                                "tool_trajectory": tool_trace,
                                "pending_approval_tool_names": pending_approval_tool_names,
                                "pending_approval_count": len(pending_approval_tool_names),
                                "failed_tools": failed_tools,
                                "recovered_tool_errors": recovered_tool_errors,
                                "unresolved_tool_errors": unresolved_tool_errors,
                                "memory_context": memory_context,
                                "final_response": final_response,
                                "candidate_count": len(plans),
                                "plan_count_limit_passed": plan_count_limit_passed,
                                "plans": metrics,
                                "candidate_time_violations": candidate_time_violations,
                                "replan_candidate_metrics": replan_metrics,
                                "clarification_detected": agent_requested_clarification,
                                "approval_interrupt_pending": approval_interrupt_pending,
                                "clarifying_question_count": clarification_question_count,
                                "clarification_question_limit_passed": question_limit_passed,
                                "clarification_targets_met": clarification_targets_met,
                                "clarification_expectation_met": (
                                    agent_requested_clarification == clarification_expectation
                                    if isinstance(clarification_expectation, bool)
                                    and selected_variant == "agent"
                                    else None
                                ),
                                "approval_expectation_met": (
                                    approval_interrupt_pending
                                    == expectations.get("approval_required")
                                    if isinstance(expectations, dict)
                                    and isinstance(expectations.get("approval_required"), bool)
                                    and selected_variant == "agent"
                                    else None
                                ),
                                "forbidden_tools_used": forbidden_tools_used,
                                "workflow_succeeded": workflow_succeeded,
                                **usage,
                            }
                            results.append(result)
                            self.stdout.write(
                                json.dumps(
                                    {
                                        key: result[key]
                                        for key in (
                                            "scenario_id",
                                            "variant",
                                            "repeat",
                                            "passed",
                                            "duration_seconds",
                                            "candidate_count",
                                            "model_call_count",
                                            "total_tokens",
                                        )
                                    },
                                    ensure_ascii=False,
                                )
                            )
                        except Exception as exc:
                            results.append(
                                {
                                    "scenario_id": scenario["id"],
                                    "split": scenario.get("split", "regression"),
                                    "variant": selected_variant,
                                    "repeat": repeat_index,
                                    "passed": False,
                                    "duration_seconds": round(perf_counter() - started, 4),
                                    "error_type": type(exc).__name__,
                                    "tool_trajectory": [],
                                    "plans": [],
                                }
                            )
                            self.stderr.write(
                                f"{scenario['id']} {selected_variant} run {repeat_index}: "
                                f"{type(exc).__name__}"
                            )
                        finally:
                            User.objects.filter(pk=user.pk).delete()
        finally:
            if audit_request_ids:
                LLMCallAudit.objects.filter(
                    request_id__in=audit_request_ids,
                    component="time_steward",
                ).delete()

        gate_results = [item for item in results if item["variant"] == "agent"] or results
        gate_passed_count = sum(bool(item.get("passed")) for item in gate_results)
        report = {
            "schema_version": "timeagent.planning-harness-evaluation.v1",
            "created_at": datetime.now(UTC).isoformat(),
            "dataset": {
                "path": str(dataset_path),
                "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            },
            "model_alias": options.get("model") or "default",
            "variant_selection": variant,
            "repeat_count": repeats,
            "holdout_included": bool(options["include_holdout"]),
            "case_count": len(scenarios),
            "run_count": len(results),
            "passed_count": sum(bool(item.get("passed")) for item in results),
            "agent_gate": {
                "run_count": len(gate_results),
                "passed_count": gate_passed_count,
            },
            "variant_summaries": self._variant_summaries(results),
            "results": results,
        }
        output_path = options.get("output")
        if output_path is None:
            output_path = (
                Path(settings.BASE_DIR)
                / "evaluation_reports"
                / f"planning-harness-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
            )
        self._write_report(output_path, report)
        self.stdout.write(f"Evaluation report: {output_path}")
        if gate_passed_count != len(gate_results):
            raise CommandError(
                "Planning Agent evaluation failed: "
                f"{gate_passed_count}/{len(gate_results)} Agent runs passed"
            )

    @staticmethod
    def _default_dataset_path() -> Path:
        return (
            Path(settings.BASE_DIR)
            / "apps"
            / "planning"
            / "fixtures"
            / ("agent_harness_scenarios_v1.json")
        )

    @staticmethod
    def _load_scenarios(path: Path) -> list[dict[str, Any]]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot load planning scenarios: {path}") from exc
        if not isinstance(document, dict) or not isinstance(document.get("scenarios"), list):
            raise CommandError("Planning scenario fixture must contain a scenarios array")
        scenarios = document["scenarios"]
        if not scenarios or any(not isinstance(item, dict) for item in scenarios):
            raise CommandError("Planning scenario fixture is empty or malformed")
        return cast(list[dict[str, Any]], scenarios)

    @staticmethod
    def _datetime(value: object) -> datetime:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError("Evaluation timestamps must include a timezone")
        return parsed

    def _seed_scenario(self, scenario: dict[str, Any]) -> tuple[User, dict[str, Any]]:
        user = User.objects.create_user(username=f"planning-eval-{uuid4().hex}")
        try:
            timezone_name = str(scenario["timezone"])
            UserPreferenceService.update_for_user(
                user,
                {
                    "timezone": timezone_name,
                    "locale": "zh-CN",
                    "workday_start": time.fromisoformat(str(scenario["workday_start"])),
                    "workday_end": time.fromisoformat(str(scenario["workday_end"])),
                },
            )
            task_map: dict[str, Any] = {}
            for raw_task in scenario["tasks"]:
                if not isinstance(raw_task, dict):
                    raise ValueError("Scenario tasks must be objects")
                key = str(raw_task["key"])
                flags = raw_task.get("flags", {})
                flags = flags if isinstance(flags, dict) else {}
                task_map[key] = TaskService.create_task(
                    CreateTaskCommand(
                        user=user,
                        title=str(raw_task["title"]),
                        description=str(raw_task.get("description", "")),
                        estimated_minutes=int(raw_task["estimated_minutes"]),
                        priority=str(raw_task.get("priority", "medium")),
                        due_at=(
                            self._datetime(raw_task["due_at"])
                            if raw_task.get("due_at") is not None
                            else None
                        ),
                        planning_locked=bool(raw_task.get("planning_locked", False)),
                        splittable=bool(flags.get("splittable", raw_task.get("splittable", False))),
                        minimum_chunk_minutes=int(raw_task.get("minimum_chunk_minutes", 30)),
                        buffer_before_minutes=int(raw_task.get("buffer_before_minutes", 0)),
                        buffer_after_minutes=int(raw_task.get("buffer_after_minutes", 0)),
                        planned_start_at=(
                            self._datetime(flags["planned_start_at"])
                            if flags.get("planned_start_at") is not None
                            else None
                        ),
                        planned_end_at=(
                            self._datetime(flags["planned_end_at"])
                            if flags.get("planned_end_at") is not None
                            else None
                        ),
                        tags=list(raw_task.get("tags", [])),
                    ),
                )
                if flags.get("status") == TaskStatus.COMPLETED:
                    task_map[key] = TaskService.complete_task(
                        task_id=task_map[key].pk,
                        user=user,
                        occurred_at=self._datetime(scenario["anchor_at"]),
                        origin="evaluation",
                    )

            for memory in scenario.get("memory_context", []):
                if not isinstance(memory, dict):
                    continue
                SemanticMemoryService.create_proposal(
                    user=user,
                    payload=MemoryProposalPayload(
                        operation="create",
                        category="scheduling_preference",
                        key=f"evaluation_{scenario['id']}",
                        value={"preference": str(memory.get("text", ""))},
                        confidence=float(memory.get("confidence", 0.9)),
                        evidence_excerpt="用户已确认的合成评测偏好",
                        reason_code="evaluation_fixture",
                    ),
                    explicit_user_authorized=True,
                    direct_apply_mode="enabled",
                    source_type="agent_tool",
                    idempotency_key=f"evaluation:{uuid4().hex}",
                )
            for raw_event in scenario.get("events", []):
                if not isinstance(raw_event, dict):
                    raise ValueError("Scenario events must be objects")
                EventService.create_event(
                    CreateEventCommand(
                        user=user,
                        title=str(raw_event["title"]),
                        start_at=self._datetime(raw_event["start_at"]),
                        end_at=self._datetime(raw_event["end_at"]),
                        timezone=timezone_name,
                        origin="evaluation",
                    )
                )
            return user, task_map
        except Exception:
            User.objects.filter(pk=user.pk).delete()
            raise

    def _invoke_agent(
        self,
        *,
        agent: Any,
        user: User,
        scenario: dict[str, Any],
        request_id: str,
        task_map: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], list[str]]:
        prompt = str(scenario["prompt"])
        anchor_at = self._datetime(scenario["anchor_at"])
        conversation_id = str(uuid4())
        context = RuntimeContext(
            user_id=str(user.pk),
            request_id=request_id,
            timezone=str(scenario["timezone"]),
            locale="zh-CN",
            current_datetime=anchor_at,
            trigger_type="user_message",
            conversation_id=conversation_id,
            input_message=prompt,
            actor=user,
        )
        result = agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content=prompt,
                        additional_kwargs={
                            "run_anchor_datetime_utc": anchor_at.astimezone(UTC).isoformat()
                        },
                    )
                ]
            },
            config={"configurable": {"thread_id": conversation_id}},
            context=context,
        )
        pending_approval_tool_names = self._pending_approval_tool_names(
            result.get("__interrupt__", [])
        )
        messages = result.get("messages", [])
        final_response = (
            str(messages[-1].content) if messages and isinstance(messages[-1], AIMessage) else ""
        )
        tool_statuses = {
            str(message.tool_call_id): message.status
            for message in messages
            if isinstance(message, ToolMessage)
        }
        tool_observations = {
            str(message.tool_call_id): str(message.content)[:12000]
            for message in messages
            if isinstance(message, ToolMessage)
        }
        task_key_by_id = {str(task.pk): key for key, task in task_map.items()}

        def remap_task_ids(value: Any) -> Any:
            if isinstance(value, str):
                return task_key_by_id.get(value, value)
            if isinstance(value, list):
                return [remap_task_ids(item) for item in value]
            if isinstance(value, dict):
                return {str(key): remap_task_ids(item) for key, item in value.items()}
            return value

        trace: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for message in messages:
            if not isinstance(message, AIMessage):
                continue
            for call in message.tool_calls:
                call_id = str(call.get("id", ""))
                if call_id and call_id in seen_ids:
                    continue
                seen_ids.add(call_id)
                trace.append(
                    {
                        "name": str(call.get("name", "")),
                        "arguments": remap_task_ids(call.get("args", {})),
                        "status": tool_statuses.get(call_id, "unknown"),
                        "observation": tool_observations.get(call_id, ""),
                    }
                )
        raw_semantic_memories = result.get("semantic_memories", [])
        raw_memory_profile = result.get("time_memory_profile")
        memory_context = {
            "semantic_memory_count": (
                len(raw_semantic_memories) if isinstance(raw_semantic_memories, list) else 0
            ),
            "behavior_profile_available": isinstance(raw_memory_profile, dict),
        }
        return final_response, trace, memory_context, pending_approval_tool_names

    @staticmethod
    def _pending_approval_tool_names(raw_interrupts: object) -> list[str]:
        """Extract tools paused at LangGraph HITL before any business write executes."""

        if not isinstance(raw_interrupts, (list, tuple)):
            return []
        names: list[str] = []
        for interrupt in raw_interrupts:
            value = getattr(interrupt, "value", None)
            if not isinstance(value, dict):
                continue
            requests = value.get("action_requests", [])
            if not isinstance(requests, list):
                continue
            names.extend(
                request["name"]
                for request in requests
                if isinstance(request, dict) and isinstance(request.get("name"), str)
            )
        return sorted(set(names))

    @classmethod
    def _plan_metrics(
        cls,
        *,
        scenario: dict[str, Any],
        plan: SchedulePlan,
        task_map: dict[str, Any],
        final_response: str,
    ) -> dict[str, Any]:
        task_key_by_id = {str(task.pk): key for key, task in task_map.items()}
        grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in task_map}
        for item in plan.items:
            if item.get("kind") == "plan_evidence":
                continue
            task_key = task_key_by_id.get(str(item.get("task_id")))
            if task_key is not None:
                grouped[task_key].append(item)

        timezone = ZoneInfo(str(scenario["timezone"]))
        scheduled_by_key: dict[str, list[tuple[datetime, datetime]]] = {}
        daily_minutes: dict[str, int] = {}
        placed_minutes = 0
        placed_segments = 0
        hard_violations: list[str] = []
        soft_checks: list[dict[str, Any]] = []
        raw_evidence: object = next(
            (
                item.get("evidence", {})
                for item in plan.items
                if item.get("kind") == "plan_evidence"
            ),
            {},
        )
        evidence = cast(dict[str, object], raw_evidence) if isinstance(raw_evidence, dict) else {}
        creation_validation = (
            evidence.get("creation_validation", {}) if isinstance(evidence, dict) else {}
        )
        if isinstance(creation_validation, dict) and creation_validation.get("valid") is not True:
            hard_violations.extend(
                f"validator:{code}"
                for code in creation_validation.get("reason_codes", ["invalid_plan"])
            )
        raw_expectations = scenario.get("expectations", {})
        expectations = raw_expectations if isinstance(raw_expectations, dict) else {}
        # Fixture `hard`/`soft` keys are human-readable label lists. Concrete
        # parameters live at the expectation object's top level.
        hard_expectations = expectations
        soft_expectations = expectations
        try:
            daily_windows = [
                (
                    date.fromisoformat(str(window["start_date"])),
                    date.fromisoformat(str(window["end_date"])),
                    time.fromisoformat(str(window["daily_start"])),
                    time.fromisoformat(str(window["daily_end"])),
                )
                for window in expectations.get("daily_availability_windows", [])
            ]
        except (KeyError, TypeError, ValueError):
            hard_violations.append("invalid_expected_daily_availability_window")
            daily_windows = []

        for task_key, items in grouped.items():
            raw_task: dict[str, Any] = next(
                (task for task in scenario["tasks"] if str(task["key"]) == task_key),
                {},
            )
            task_flags = raw_task.get("flags", {})
            if task_flags.get("status") in {TaskStatus.COMPLETED, TaskStatus.CANCELLED} and items:
                hard_violations.append(f"terminal_task_scheduled:{task_key}")
            rows: list[tuple[datetime, datetime]] = []
            for item in items:
                if item.get("state") != "placed":
                    continue
                start = cls._datetime(item["start_at"])
                end = cls._datetime(item["end_at"])
                local_start = start.astimezone(timezone)
                local_end = end.astimezone(timezone)
                rows.append((start, end))
                placed_minutes += int(item.get("planned_duration_minutes", 0))
                placed_segments += 1
                day_key = local_start.date().isoformat()
                daily_minutes[day_key] = daily_minutes.get(day_key, 0) + int(
                    item.get("planned_duration_minutes", 0)
                )
                if local_start.weekday() >= 5 and hard_expectations.get("no_weekend") is True:
                    hard_violations.append(f"weekend:{task_key}")
                if not (
                    cls._datetime(scenario["range_start"]) <= start
                    and end <= cls._datetime(scenario["range_end"])
                ):
                    hard_violations.append(f"outside_range:{task_key}")
                if local_start.date() != local_end.date():
                    hard_violations.append(f"cross_day:{task_key}")
                if local_start.time().replace(tzinfo=None) < time.fromisoformat(
                    str(scenario["workday_start"])
                ):
                    hard_violations.append(f"before_workday:{task_key}")
                if local_end.time().replace(tzinfo=None) > time.fromisoformat(
                    str(scenario["workday_end"])
                ):
                    hard_violations.append(f"after_workday:{task_key}")
                for (
                    window_start_date,
                    window_end_date,
                    window_daily_start,
                    window_daily_end,
                ) in daily_windows:
                    if window_start_date <= local_start.date() <= window_end_date:
                        if (
                            local_start.time().replace(tzinfo=None) < window_daily_start
                            or local_end.time().replace(tzinfo=None) > window_daily_end
                        ):
                            hard_violations.append(f"daily_availability_window:{task_key}")
                raw_due = next(
                    (
                        task.get("due_at")
                        for task in scenario["tasks"]
                        if str(task["key"]) == task_key
                    ),
                    None,
                )
                if raw_due and end > cls._datetime(raw_due):
                    hard_violations.append(f"deadline:{task_key}")
                for raw_event in scenario.get("events", []):
                    event_start = cls._datetime(raw_event["start_at"])
                    event_end = cls._datetime(raw_event["end_at"])
                    if start < event_end and event_start < end:
                        hard_violations.append(f"event_overlap:{task_key}:{raw_event['title']}")
            if rows:
                scheduled_by_key[task_key] = rows

        task_titles = {str(task["key"]): str(task["title"]) for task in scenario["tasks"]}
        response_year = cls._datetime(scenario["anchor_at"]).astimezone(timezone).year
        for task_key, intervals in scheduled_by_key.items():
            title = task_titles.get(task_key, "")
            expected_days = {start.astimezone(timezone).date() for start, _ in intervals}
            response_days = cls._schedule_days_in_response(
                final_response,
                title=title,
                year=response_year,
            )
            if response_days and not response_days.issubset(expected_days):
                hard_violations.append(f"final_schedule_date_mismatch:{task_key}")

        for constraint in soft_expectations.get("precedence", []):
            before = str(constraint["before"])
            after = str(constraint["after"])
            gap_days = int(constraint.get("min_gap_days", constraint.get("minimum_gap_days", 0)))
            if before not in scheduled_by_key or after not in scheduled_by_key:
                soft_checks.append({"name": f"precedence:{before}->{after}", "passed": False})
                continue
            before_end = max(end for _, end in scheduled_by_key[before])
            after_start = min(start for start, _ in scheduled_by_key[after])
            soft_checks.append(
                {
                    "name": f"precedence:{before}->{after}",
                    "passed": after_start >= before_end + timedelta(days=gap_days),
                }
            )

        for constraint in soft_expectations.get("separation_constraints", []):
            task_keys = [str(key) for key in constraint.get("task_keys", [])]
            minimum_gap = timedelta(days=int(constraint.get("minimum_gap_days", 0)))
            task_intervals = [scheduled_by_key.get(key, []) for key in task_keys]
            separated = len(task_intervals) == 2 and all(task_intervals)
            if separated:
                separated = all(
                    (
                        right_start - left_end
                        if left_end <= right_start
                        else left_start - right_end
                        if right_end <= left_start
                        else timedelta()
                    )
                    >= minimum_gap
                    for left_start, left_end in task_intervals[0]
                    for right_start, right_end in task_intervals[1]
                )
            soft_checks.append(
                {
                    "name": f"separation:{'->'.join(task_keys)}",
                    "passed": bool(separated),
                }
            )

        all_intervals = [
            (task_key, start, end)
            for task_key, intervals in scheduled_by_key.items()
            for start, end in intervals
        ]
        for index, (left_key, left_start, left_end) in enumerate(all_intervals):
            for right_key, right_start, right_end in all_intervals[index + 1 :]:
                if left_key != right_key and left_start < right_end and right_start < left_end:
                    hard_violations.append(f"task_overlap:{left_key}:{right_key}")

        for phase in soft_expectations.get("phase_windows", []):
            phase_start = cls._datetime(phase["not_before"])
            phase_end = cls._datetime(phase["not_after"])
            task_keys = [str(key) for key in phase.get("task_keys", [])]
            within = all(
                key in scheduled_by_key
                and all(
                    phase_start <= start and end <= phase_end
                    for start, end in scheduled_by_key[key]
                )
                for key in task_keys
            )
            soft_checks.append({"name": f"phase_window:{phase.get('name', '')}", "passed": within})

        distinct_days = {
            start.astimezone(timezone).date().isoformat()
            for intervals in scheduled_by_key.values()
            for start, _ in intervals
        }
        distinct_weeks = {
            start.astimezone(timezone).isocalendar().week
            for intervals in scheduled_by_key.values()
            for start, _ in intervals
        }
        min_days = int(soft_expectations.get("min_distinct_days", 0))
        if min_days:
            soft_checks.append(
                {"name": "min_distinct_days", "passed": len(distinct_days) >= min_days}
            )
        min_weeks = int(soft_expectations.get("min_distinct_weeks", 0))
        if min_weeks:
            soft_checks.append(
                {"name": "min_distinct_weeks", "passed": len(distinct_weeks) >= min_weeks}
            )
        max_daily = soft_expectations.get("max_daily_minutes")
        if max_daily is not None:
            daily_limit_passed = max(daily_minutes.values(), default=0) <= int(max_daily)
            soft_checks.append(
                {
                    "name": "max_daily_minutes",
                    "passed": daily_limit_passed,
                }
            )
            if "max_daily_minutes" in expectations.get("hard", []) and not daily_limit_passed:
                hard_violations.append("max_daily_minutes")
        max_unplaced = soft_expectations.get("max_unplaced")
        if max_unplaced is not None:
            unplaced = sum(
                1
                for task_key, items in grouped.items()
                if not any(item.get("state") == "placed" for item in items)
                and not any(
                    task["key"] == task_key
                    and task.get("flags", {}).get("status")
                    in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
                    for task in scenario["tasks"]
                )
            )
            soft_checks.append({"name": "max_unplaced", "passed": unplaced <= int(max_unplaced)})
        for task_key in soft_expectations.get("must_schedule_task_keys", []):
            soft_checks.append(
                {"name": f"must_schedule:{task_key}", "passed": task_key in scheduled_by_key}
            )
        for task_key in soft_expectations.get("preferred_unplaced_task_keys", []):
            soft_checks.append(
                {
                    "name": f"preferred_unplaced:{task_key}",
                    "passed": task_key not in scheduled_by_key,
                }
            )
        for task_key in expectations.get("preserve_completed_task_keys", []):
            task: dict[str, Any] = next(
                (row for row in scenario["tasks"] if row["key"] == task_key),
                {},
            )
            flags = task.get("flags", {})
            soft_checks.append(
                {
                    "name": f"preserve_completed:{task_key}",
                    "passed": flags.get("status") == TaskStatus.COMPLETED
                    and task_key not in scheduled_by_key,
                }
            )
        should_ask = expectations.get("ask_planning_clarification")
        if isinstance(should_ask, bool):
            soft_checks.append(
                {
                    "name": "ask_planning_clarification",
                    "passed": cls._asks_planning_clarification(final_response) == should_ask,
                }
            )
        if expectations.get("ask_user_about_task_keys"):
            task_names = {str(task["key"]): str(task["title"]) for task in scenario["tasks"]}
            response_has_target = all(
                task_key in final_response or task_names.get(task_key, "") in final_response
                for task_key in expectations["ask_user_about_task_keys"]
            )
            soft_checks.append(
                {"name": "clarification_names_competing_tasks", "passed": response_has_target}
            )

        return {
            "plan_id": str(plan.pk),
            "status": plan.status,
            "placed_task_count": len(scheduled_by_key),
            "task_count": sum(
                1
                for key in task_map
                if not any(
                    task["key"] == key
                    and task.get("flags", {}).get("status")
                    in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
                    for task in scenario["tasks"]
                )
            ),
            "unplaced_task_keys": sorted(
                key
                for key in set(task_map) - set(scheduled_by_key)
                if not any(
                    task["key"] == key
                    and task.get("flags", {}).get("status")
                    in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
                    for task in scenario["tasks"]
                )
            ),
            "placed_minutes": placed_minutes,
            "placed_segments": placed_segments,
            "distinct_days": sorted(distinct_days),
            "distinct_weeks": sorted(distinct_weeks),
            "daily_minutes": daily_minutes,
            "schedule": {
                key: [
                    {"start_at": start.isoformat(), "end_at": end.isoformat()}
                    for start, end in intervals
                ]
                for key, intervals in scheduled_by_key.items()
            },
            "creation_validation": creation_validation,
            "hard_violations": sorted(set(hard_violations)),
            "soft_checks": soft_checks,
            "soft_check_pass_rate": (
                round(sum(item["passed"] for item in soft_checks) / len(soft_checks), 4)
                if soft_checks
                else None
            ),
        }

    @staticmethod
    def _plan_count_limit_passed(*, candidate_count: int, maximum: object) -> bool:
        return (
            not isinstance(maximum, int) or isinstance(maximum, bool) or candidate_count <= maximum
        )

    @staticmethod
    def _asks_planning_clarification(response: str) -> bool:
        normalized = re.sub(r"\s+", " ", response)
        return bool(
            re.search(
                r"优先.{0,24}(?:哪|哪个|哪一|选择|先)|"
                r"安排.{0,24}(?:哪|哪个|哪一项|哪一天|哪天)|"
                r"(?:哪|哪个|哪一项|哪一天|哪天|什么时间|哪个时段).{0,24}"
                r"(?:优先|安排|选择|任务|客户|时间|时段|日期)|"
                r"你希望.{0,24}(?:优先|哪|哪个|哪一|日期|时间|时段|顺序|怎么处理|如何安排)|"
                r"请(?:问|先)?(?:选择|决定|确认|告诉我|补充).{0,24}"
                r"(?:优先|哪|哪个|范围|日期|时间|时段|可用|顺序|客户|任务)|"
                r"(?:需要你|需要您).{0,24}(?:决定|选择|补充|告诉|优先|范围|日期|时间|时段)|"
                r"(?:怎么|如何).{0,12}(?:处理|安排|排入|选择)",
                normalized,
            )
        )

    @staticmethod
    def _asks_clarification(response: str) -> bool:
        normalized = re.sub(r"\s+", " ", response)
        return bool(
            re.search(
                r"请问.{0,24}(?:优先|哪项|哪个|哪些|范围|日期)|"
                r"请确认.{0,24}(?:优先|哪项|哪个|顺序|范围|日期)|"
                r"(?:请确认|请回复|请答复).{0,40}(?:是否|哪|哪个|优先|移到|改到|选择|同意)|"
                r"你希望.{0,24}(?:优先|哪项|哪个|顺序|范围|日期)|"
                r"需要你.{0,16}(?:决定|选择|确认优先|告诉我.{0,8}(?:优先|哪项|哪个))|"
                r"需要你确认|等你确认|确认后(?:我|再)|是否确认|"
                r"(?:需要我|要我).{0,20}(?:提交|改期|执行|重排|移动)|"
                r"(?:你|您).{0,20}(?:哪一个|哪一项|哪种).{0,4}[？?]|"
                r"请(?:先)?(?:决定|选择|告诉我|回复|答复).{0,24}(?:优先|哪项|哪个|哪一个|是否)|"
                r"更倾向.{0,16}(?:哪项|哪个|哪种|哪一个)|"
                r"请选择.{0,16}(?:任务|优先|顺序|方案)|"
                r"请告诉我.{0,16}(?:优先|哪项|哪个|顺序|范围)",
                normalized,
            )
        )

    @classmethod
    def _clarifying_question_count(cls, response: str) -> int:
        chunks = re.split(r"(?<=[?？])", response)
        count = sum(cls._asks_planning_clarification(chunk) for chunk in chunks)
        return count if count else int(cls._asks_planning_clarification(response))

    @staticmethod
    def _schedule_days_in_response(response: str, *, title: str, year: int) -> set[date]:
        date_pattern = re.compile(r"(?<!\d)(\d{1,2})\s*(?:/|-|月)\s*(\d{1,2})日?")
        heading_pattern = re.compile(
            r"(\d{1,2})\s*(?:月|/|-)\s*(\d{1,2})\s*日?(?:\s*[（(].*?[）)])?"
        )
        section_day: date | None = None
        scheduled_days: set[date] = set()
        for line in response.splitlines():
            cleaned = line.strip().strip("*#_ ").strip()
            heading = heading_pattern.fullmatch(cleaned)
            if heading is not None:
                try:
                    section_day = date(year, int(heading.group(1)), int(heading.group(2)))
                except ValueError:
                    section_day = None
                continue
            if not title or title not in line:
                continue
            before_title = line.split(title, maxsplit=1)[0]
            match = date_pattern.search(before_title)
            if match is not None:
                has_schedule_time_before_title = bool(
                    re.search(
                        r"\d{1,2}:\d{2}\s*[–—-]\s*\d{1,2}:\d{2}",
                        before_title,
                    )
                )
                has_deadline_context = bool(
                    re.search(r"截止|截至|deadline|due date", line, re.IGNORECASE)
                )
                if has_deadline_context and not has_schedule_time_before_title:
                    match = None
            if match is not None:
                try:
                    scheduled_days.add(date(year, int(match.group(1)), int(match.group(2))))
                except ValueError:
                    continue
            elif section_day is not None:
                scheduled_days.add(section_day)
        return scheduled_days

    @staticmethod
    def _classify_tool_errors(
        tool_trace: list[dict[str, Any]],
    ) -> tuple[list[str], list[str]]:
        recovered: list[str] = []
        unresolved: list[str] = []
        for index, call in enumerate(tool_trace):
            if call.get("status") != "error":
                continue
            tool_name = str(call.get("name", ""))
            later_recovery = any(
                later.get("name") == tool_name and later.get("status") == "success"
                for later in tool_trace[index + 1 :]
            )
            (recovered if later_recovery else unresolved).append(tool_name)
        return recovered, unresolved

    @staticmethod
    def _clarification_targets_met(
        scenario: dict[str, Any],
        response: str,
        *,
        tool_trace: list[dict[str, Any]] | None = None,
    ) -> bool:
        raw_expectations = scenario.get("expectations", {})
        expectations = raw_expectations if isinstance(raw_expectations, dict) else {}
        raw_aliases = expectations.get("ask_user_task_aliases", {})
        aliases = raw_aliases if isinstance(raw_aliases, dict) else {}
        task_rows = scenario.get("tasks", [])
        for task_key in expectations.get("ask_user_about_task_keys", []):
            key = str(task_key)
            task = next(
                (
                    item
                    for item in task_rows
                    if isinstance(item, dict) and str(item.get("key")) == key
                ),
                {},
            )
            candidates = [key, str(task.get("title", ""))]
            raw_task_aliases = aliases.get(key, [])
            if isinstance(raw_task_aliases, list):
                candidates.extend(str(alias) for alias in raw_task_aliases)
            named_in_response = any(candidate and candidate in response for candidate in candidates)
            named_in_action = any(
                call.get("name") == "reschedule_task"
                and isinstance(call.get("arguments"), dict)
                and str(call["arguments"].get("task_id", "")) == key
                for call in tool_trace or []
            )
            if not named_in_response and not named_in_action:
                return False
        return True

    @staticmethod
    def _candidate_time_violations(
        response: str,
        *,
        scenario: dict[str, Any],
        tool_trace: list[dict[str, Any]],
    ) -> list[str]:
        timezone = ZoneInfo(str(scenario["timezone"]))
        anchor_year = Command._datetime(scenario["anchor_at"]).astimezone(timezone).year
        workday_start = time.fromisoformat(str(scenario["workday_start"]))
        workday_end = time.fromisoformat(str(scenario["workday_end"]))
        date_pattern = re.compile(r"(?<!\d)(\d{1,2})\s*(?:/|-|月)\s*(\d{1,2})日?")
        heading_pattern = re.compile(
            r"(\d{1,2})\s*(?:月|/|-)\s*(\d{1,2})\s*日?(?:\s*[（(].*?[）)])?"
        )
        time_range_pattern = re.compile(
            r"(?<!\d)(\d{1,2}):(\d{2})\s*[–—-]\s*(\d{1,2}):(\d{2})(?!\d)"
        )
        suggestion_pattern = re.compile(
            r"建议的新时间|建议时段|建议.{0,8}(?:改到|移到|安排到|挪到)|"
            r"(?:改到|移到|挪到|候选时段)"
        )
        free_slots: list[tuple[datetime, datetime]] = []
        for call in tool_trace:
            arguments = call.get("arguments", {})
            if (
                call.get("name") != "get_planning_context"
                or call.get("status") != "success"
                or not isinstance(arguments, dict)
                or arguments.get("mode") != "free_slots"
            ):
                continue
            try:
                observation = json.loads(str(call.get("observation", "")))
            except json.JSONDecodeError:
                continue
            if not isinstance(observation, dict):
                continue
            raw_slots = observation.get("free_slots", [])
            if not isinstance(raw_slots, list):
                continue
            for raw_slot in raw_slots:
                if not isinstance(raw_slot, dict):
                    continue
                try:
                    free_slots.append(
                        (
                            datetime.fromisoformat(str(raw_slot["start_at"])),
                            datetime.fromisoformat(str(raw_slot["end_at"])),
                        )
                    )
                except (KeyError, ValueError):
                    continue

        violations: list[str] = []
        section_day: date | None = None
        for line in response.splitlines():
            cleaned = line.strip().strip("*#_ ").strip()
            heading = heading_pattern.fullmatch(cleaned)
            if heading is not None:
                try:
                    section_day = date(anchor_year, int(heading.group(1)), int(heading.group(2)))
                except ValueError:
                    section_day = None
            if not suggestion_pattern.search(line):
                continue
            for match in time_range_pattern.finditer(line):
                date_match = date_pattern.search(line)
                candidate_day: date | None
                if date_match is not None:
                    try:
                        candidate_day = date(
                            anchor_year,
                            int(date_match.group(1)),
                            int(date_match.group(2)),
                        )
                    except ValueError:
                        violations.append("suggested_time_has_invalid_date")
                        continue
                else:
                    candidate_day = section_day
                if candidate_day is None:
                    violations.append("suggested_time_has_no_date")
                    continue
                candidate_start = datetime.combine(
                    candidate_day,
                    time(int(match.group(1)), int(match.group(2))),
                    tzinfo=timezone,
                )
                candidate_end = datetime.combine(
                    candidate_day,
                    time(int(match.group(3)), int(match.group(4))),
                    tzinfo=timezone,
                )
                if candidate_start.time() < workday_start or candidate_end.time() > workday_end:
                    violations.append("suggested_time_outside_work_hours")
                has_slot_evidence = any(
                    slot_start.astimezone(timezone) <= candidate_start
                    and candidate_end <= slot_end.astimezone(timezone)
                    for slot_start, slot_end in free_slots
                )
                if not has_slot_evidence:
                    violations.append("suggested_time_missing_free_slot_evidence")
        task_due = {
            str(task["key"]): Command._datetime(str(task["due_at"]))
            for task in scenario.get("tasks", [])
            if isinstance(task, dict) and task.get("due_at")
        }
        for call in tool_trace:
            if call.get("name") != "reschedule_task":
                continue
            arguments = call.get("arguments", {})
            if not isinstance(arguments, dict):
                violations.append("reschedule_tool_arguments_invalid")
                continue
            try:
                candidate_start = datetime.fromisoformat(str(arguments["planned_start_at"]))
                candidate_end = datetime.fromisoformat(str(arguments["planned_end_at"]))
            except (KeyError, ValueError):
                violations.append("reschedule_tool_arguments_invalid")
                continue
            if (
                candidate_start.utcoffset() is None
                or candidate_end.utcoffset() is None
                or candidate_end <= candidate_start
            ):
                violations.append("reschedule_tool_arguments_invalid")
                continue
            local_start = candidate_start.astimezone(timezone)
            local_end = candidate_end.astimezone(timezone)
            if (
                local_start.time().replace(tzinfo=None) < workday_start
                or local_end.time().replace(tzinfo=None) > workday_end
            ):
                violations.append("reschedule_tool_time_outside_work_hours")
            if not any(
                slot_start.astimezone(timezone) <= local_start
                and local_end <= slot_end.astimezone(timezone)
                for slot_start, slot_end in free_slots
            ):
                violations.append("reschedule_tool_time_missing_free_slot_evidence")
            task_key = str(arguments.get("task_id", ""))
            if task_key in task_due and candidate_end > task_due[task_key]:
                violations.append("reschedule_tool_time_after_deadline")
        return sorted(set(violations))

    @staticmethod
    def _replan_candidate_metrics(
        *,
        response: str,
        scenario: dict[str, Any],
        tool_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raw_expectations = scenario.get("expectations", {})
        expectations = raw_expectations if isinstance(raw_expectations, dict) else {}
        expected_keys = [str(key) for key in expectations.get("expected_moved_task_keys", [])]
        if not expected_keys:
            return {}

        timezone = ZoneInfo(str(scenario["timezone"]))
        year = Command._datetime(str(scenario["anchor_at"])).astimezone(timezone).year
        move_pattern = re.compile(r"(?:移到|改到|挪到|安排到|改期至|重排到)")
        date_pattern = re.compile(r"(?<!\d)(\d{1,2})\s*(?:/|-|月)\s*(\d{1,2})日?")
        time_pattern = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})\s*[–—-]\s*(\d{1,2}):(\d{2})(?!\d)")
        candidate_rows: list[tuple[str, datetime, datetime]] = []
        task_by_key = {
            str(task["key"]): task for task in scenario.get("tasks", []) if isinstance(task, dict)
        }
        for call in tool_trace:
            if call.get("name") != "reschedule_task":
                continue
            arguments = call.get("arguments", {})
            if not isinstance(arguments, dict):
                continue
            try:
                start_at = datetime.fromisoformat(str(arguments["planned_start_at"]))
                end_at = datetime.fromisoformat(str(arguments["planned_end_at"]))
            except (KeyError, ValueError):
                continue
            candidate_rows.append((str(arguments.get("task_id", "")), start_at, end_at))

        if not candidate_rows:
            for line in response.splitlines():
                if not move_pattern.search(line):
                    continue
                date_match = date_pattern.search(line)
                if date_match is None:
                    continue
                try:
                    candidate_day = date(year, int(date_match.group(1)), int(date_match.group(2)))
                except ValueError:
                    continue
                time_match = time_pattern.search(line)
                if time_match is None:
                    continue
                candidate_rows.append(
                    (
                        expected_keys[0] if len(expected_keys) == 1 else "",
                        datetime.combine(
                            candidate_day,
                            time(int(time_match.group(1)), int(time_match.group(2))),
                            tzinfo=timezone,
                        ),
                        datetime.combine(
                            candidate_day,
                            time(int(time_match.group(3)), int(time_match.group(4))),
                            tzinfo=timezone,
                        ),
                    )
                )

        selected_by_task: dict[str, tuple[datetime, datetime]] = {}
        for task_key, start_at, end_at in candidate_rows:
            if task_key not in expected_keys and len(expected_keys) == 1:
                task_key = expected_keys[0]
            if task_key in expected_keys:
                selected_by_task.setdefault(task_key, (start_at, end_at))

        shifts: dict[str, int] = {}
        for task_key, (start_at, end_at) in selected_by_task.items():
            flags = task_by_key.get(task_key, {}).get("flags", {})
            try:
                old_start = datetime.fromisoformat(str(flags["planned_start_at"]))
                old_end = datetime.fromisoformat(str(flags["planned_end_at"]))
            except (KeyError, TypeError, ValueError):
                continue
            shifts[task_key] = round(
                abs((start_at - old_start).total_seconds() / 60)
                + abs((end_at - old_end).total_seconds() / 60)
            )

        max_moved_tasks = expectations.get("max_moved_tasks")
        max_total_shift = expectations.get("max_total_shift_minutes")
        moved_keys_met = set(selected_by_task) == set(expected_keys)
        moved_count_met = (
            not isinstance(max_moved_tasks, int) or len(selected_by_task) <= max_moved_tasks
        )
        total_shift = sum(shifts.values())
        shift_limit_met = (
            not isinstance(max_total_shift, int)
            or len(shifts) == len(expected_keys)
            and total_shift <= max_total_shift
        )

        free_slots: list[tuple[datetime, datetime]] = []
        for call in tool_trace:
            if (
                call.get("name") != "get_planning_context"
                or call.get("status") != "success"
                or not isinstance(call.get("arguments"), dict)
                or call["arguments"].get("mode") != "free_slots"
            ):
                continue
            try:
                observation = json.loads(str(call.get("observation", "")))
            except json.JSONDecodeError:
                continue
            if isinstance(observation, dict) and isinstance(observation.get("free_slots"), list):
                for slot in observation["free_slots"]:
                    if not isinstance(slot, dict):
                        continue
                    try:
                        free_slots.append(
                            (
                                datetime.fromisoformat(str(slot["start_at"])),
                                datetime.fromisoformat(str(slot["end_at"])),
                            )
                        )
                    except (KeyError, ValueError):
                        continue

        minimum_shift_met = True
        for task_key, selected_shift in shifts.items():
            old_start = datetime.fromisoformat(
                str(task_by_key[task_key]["flags"]["planned_start_at"])
            )
            old_end = datetime.fromisoformat(str(task_by_key[task_key]["flags"]["planned_end_at"]))
            possible_shifts = [
                round(
                    abs((slot_start - old_start).total_seconds() / 60)
                    + abs((slot_end - old_end).total_seconds() / 60)
                )
                for slot_start, slot_end in free_slots
                if slot_end - slot_start == old_end - old_start
            ]
            if possible_shifts and selected_shift > min(possible_shifts):
                minimum_shift_met = False

        checks = {
            "expected_moved_tasks": moved_keys_met,
            "max_moved_tasks": moved_count_met,
            "max_total_shift_minutes": shift_limit_met,
            "minimum_available_shift": minimum_shift_met,
        }
        return {
            "passed": all(checks.values()),
            "selected_task_keys": sorted(selected_by_task),
            "shift_minutes_by_task": shifts,
            "total_shift_minutes": total_shift,
            "minimum_available_shift_met": minimum_shift_met,
            "checks": checks,
        }

    @staticmethod
    def _task_facts(scenario: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "key": str(task["key"]),
                "title": str(task["title"]),
                "description": str(task.get("description", "")),
                "estimated_minutes": int(task["estimated_minutes"]),
                "priority": str(task.get("priority", "medium")),
                "due_at": task.get("due_at"),
            }
            for task in scenario["tasks"]
        ]

    @staticmethod
    def _usage_for_request(request_id: str) -> dict[str, int | None]:
        rows = list(
            LLMCallAudit.objects.filter(request_id=request_id, component="time_steward").values(
                "status", "total_tokens", "duration_ms"
            )
        )
        completed = [row for row in rows if row["status"] == "completed"]
        token_values = [int(row["total_tokens"]) for row in completed if row["total_tokens"]]
        return {
            "model_call_count": len(rows),
            "completed_model_call_count": len(completed),
            "total_tokens": sum(token_values) if token_values else None,
            "model_duration_ms": sum(int(row["duration_ms"]) for row in completed),
        }

    @staticmethod
    def _write_report(path: Path, document: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _variant_summaries(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        summaries: dict[str, dict[str, Any]] = {}
        for variant in ("baseline", "agent"):
            selected = [item for item in results if item.get("variant") == variant]
            if not selected:
                continue
            latencies = sorted(float(item["duration_seconds"]) for item in selected)
            p95_index = min(len(latencies) - 1, ceil(len(latencies) * 0.95) - 1)
            token_values = [
                int(item["total_tokens"])
                for item in selected
                if item.get("total_tokens") is not None
            ]
            call_values = [
                int(item["model_call_count"])
                for item in selected
                if item.get("model_call_count") is not None
            ]
            plans = [
                plan
                for item in selected
                for plan in item.get("plans", [])
                if isinstance(plan, dict)
            ]
            soft_values = [
                float(plan["soft_check_pass_rate"])
                for plan in plans
                if plan.get("soft_check_pass_rate") is not None
            ]
            clarification_cases = [
                item for item in selected if item.get("clarification_expectation_met") is not None
            ]
            approval_cases = [
                item for item in selected if item.get("approval_expectation_met") is not None
            ]
            summaries[variant] = {
                "run_count": len(selected),
                "passed_count": sum(bool(item.get("passed")) for item in selected),
                "mean_latency_seconds": round(sum(latencies) / len(latencies), 4),
                "p50_latency_seconds": round(latencies[len(latencies) // 2], 4),
                "p95_latency_seconds": round(latencies[p95_index], 4),
                "mean_model_calls": (
                    round(sum(call_values) / len(call_values), 4) if call_values else None
                ),
                "total_tokens": sum(token_values) if token_values else None,
                "mean_tokens_per_run": (
                    round(sum(token_values) / len(token_values), 2) if token_values else None
                ),
                "mean_soft_check_pass_rate": (
                    round(sum(soft_values) / len(soft_values), 4) if soft_values else None
                ),
                "clarification_expectation_cases": len(clarification_cases),
                "clarification_expectation_met": sum(
                    bool(item.get("clarification_expectation_met")) for item in clarification_cases
                ),
                "approval_expectation_cases": len(approval_cases),
                "approval_expectation_met": sum(
                    bool(item.get("approval_expectation_met")) for item in approval_cases
                ),
                "tool_error_attempt_count": sum(
                    len(item.get("failed_tools", [])) for item in selected
                ),
                "recovered_tool_error_count": sum(
                    len(item.get("recovered_tool_errors", [])) for item in selected
                ),
                "unresolved_tool_error_run_count": sum(
                    bool(item.get("unresolved_tool_errors")) for item in selected
                ),
            }
        return summaries
