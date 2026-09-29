"""Run a synthetic, single-day schedule trajectory against the real Time Steward agent.

This command creates and removes one isolated Django user. It never approves HITL
interrupts and writes a result file only when --output is supplied.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db.models import Count
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.store.memory import InMemoryStore

from apps.action_proposals.models import ActionProposal
from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.context import RuntimeContext
from apps.agents.model import build_chat_model
from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.events.services import CreateEventCommand, EventQuery, EventService
from apps.observability.models import LLMCallAudit
from apps.planning.models import SchedulePlan, SchedulePlanStatus
from apps.preferences.services import UserPreferenceService
from apps.tasks.models import Task, TaskPriority, TaskStatus
from apps.tasks.services import CreateTaskCommand, TaskService, UpdateTaskCommand
from common.time import to_utc

DEFAULT_DAY = date(2026, 10, 5)  # Monday; fixed by default for reproducibility.
TIMEZONE_NAME = "Asia/Shanghai"
LOCALE = "zh-CN"


def _local_anchor(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=ZoneInfo(TIMEZONE_NAME))


def trajectory_steps(day: date) -> list[dict[str, Any]]:
    """Return a small, ordered whole-day sequence of user-visible check-ins."""

    return [
        {
            "id": "08_initial_plan",
            "anchor": _local_anchor(day, 8),
            "prompt": (
                "请根据我今天剩余的任务和工作时间安排一个日程草案。优先处理有截止时间的任务，"
                "保留午间空档；只生成可审阅的草案，不要直接改动或应用日历。"
            ),
            "mutation": None,
        },
        {
            "id": "10_done",
            "anchor": _local_anchor(day, 10),
            "prompt": (
                "收件箱分拣已经提前完成。请从余下任务中移除它，检查当前草案是否仍合适；"
                "如果无需调整就说明保持原安排。任何需要审批的实际改动都先停下来。"
            ),
            "mutation": "complete_inbox",
        },
        {
            "id": "11_30_overrun",
            "anchor": _local_anchor(day, 11, 30),
            "prompt": (
                "会议纪要整理比预估多花了30分钟，现在还需要90分钟。请重新检查截止时间和"
                "工作时段约束；如果原安排仍可行就保持，不可行时给我更新草案。"
            ),
            "mutation": "extend_minutes",
        },
        {
            "id": "13_meeting_added",
            "anchor": _local_anchor(day, 13),
            "prompt": (
                "我刚增加了一个13:00到14:00的会议。请结合这个日历事实检查草案，"
                "只在确有必要时重新安排；不要自动批准或应用任何变更。"
            ),
            "mutation": "add_meeting",
        },
        {
            "id": "15_task_cancelled",
            "anchor": _local_anchor(day, 15),
            "prompt": (
                "客户资料整理任务取消了。请确认剩余任务和截止时间是否仍能满足；"
                "如果变化不值得重排，请保持稳定。"
            ),
            "mutation": "cancel_records",
        },
        {
            "id": "16_urgent_added",
            "anchor": _local_anchor(day, 16),
            "prompt": (
                "新增紧急缺陷修复，预计45分钟，今天18:00前完成。请评估如何安排，"
                "保留工作时间和其他任务截止约束；需要改动时生成草案，不要应用。"
            ),
            "mutation": "add_urgent",
        },
    ]


def _plan_slots(items: Sequence[dict[str, Any]]) -> dict[str, list[tuple[datetime, datetime]]]:
    slots: dict[str, list[tuple[datetime, datetime]]] = {}
    for item in items:
        task_id = item.get("task_id")
        start_at = item.get("start_at")
        end_at = item.get("end_at")
        if not task_id or item.get("state") != "placed":
            continue
        try:
            start = datetime.fromisoformat(str(start_at))
            end = datetime.fromisoformat(str(end_at))
        except ValueError:
            continue
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            continue
        slots.setdefault(str(task_id), []).append((start, end))
    for task_slots in slots.values():
        task_slots.sort(key=lambda row: row[0])
    return slots


def compare_schedule_snapshots(
    previous: dict[str, list[tuple[datetime, datetime]]],
    current: dict[str, list[tuple[datetime, datetime]]],
) -> dict[str, int]:
    """Compare task-level placements and approximate how far they shifted."""

    moved = 0
    shift_minutes = 0
    for task_id in previous.keys() | current.keys():
        old = previous.get(task_id, [])
        new = current.get(task_id, [])
        if old == new:
            continue
        moved += 1
        paired = min(len(old), len(new))
        shift_minutes += sum(
            round(abs((new[index][0] - old[index][0]).total_seconds()) / 60)
            for index in range(paired)
        )
        shift_minutes += sum(
            round((end - start).total_seconds() / 60) for start, end in old[paired:]
        )
        shift_minutes += sum(
            round((end - start).total_seconds() / 60) for start, end in new[paired:]
        )
    return {"moved_task_count": moved, "total_shift_minutes": shift_minutes}


def _extract_interrupt_tool_names(
    interrupts: object,
    messages: Sequence[Any],
) -> list[str]:
    """Extract names only; never include the interrupt payload or its arguments."""

    names: set[str] = set()
    if isinstance(interrupts, (list, tuple)):
        for interrupt in interrupts:
            value = getattr(interrupt, "value", None)
            if not isinstance(value, dict):
                continue
            requests = value.get("action_requests", [])
            if isinstance(requests, list):
                for request in requests:
                    if isinstance(request, dict):
                        name = request.get("name") or request.get("tool_name")
                        if isinstance(name, str):
                            names.add(name)
    if interrupts:
        for message in messages:
            if not isinstance(message, AIMessage):
                continue
            for call in message.tool_calls:
                if call.get("name") in {
                    "apply_schedule_plan",
                    "reschedule_task",
                    "update_task",
                    "complete_task",
                    "cancel_task",
                    "create_event",
                    "create_task",
                }:
                    names.add(str(call["name"]))
    return sorted(names)


class Command(BaseCommand):
    help = (
        "Evaluate one synthetic whole-day trajectory with the real Time Steward harness "
        "using a temporary isolated user; HITL approvals are never resumed."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--model",
            help="Configured model alias; defaults to agent.default_model.",
        )
        parser.add_argument(
            "--date",
            dest="evaluation_date",
            default=DEFAULT_DAY.isoformat(),
            help=f"Local synthetic date in YYYY-MM-DD format (default: {DEFAULT_DAY.isoformat()}).",
        )
        parser.add_argument(
            "--output",
            type=Path,
            help="Optional path for a sanitized JSON report.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        self._ensure_local_evaluation_database()
        try:
            day = date.fromisoformat(str(options["evaluation_date"]))
        except ValueError as exc:
            raise CommandError("--date must use YYYY-MM-DD format") from exc
        if day.weekday() >= 5:
            raise CommandError("--date must be a weekday because the synthetic profile is Mon-Fri")

        model_alias = options.get("model")
        agent = build_time_steward_agent(
            model=build_chat_model(model_alias),
            store=InMemoryStore(),
        )
        user = User.objects.create_user(username=f"day-trajectory-eval-{uuid4().hex}")
        request_ids: list[str] = []
        try:
            UserPreferenceService.update_for_user(
                user,
                {
                    "timezone": TIMEZONE_NAME,
                    "locale": LOCALE,
                    "workday_start": time(9),
                    "workday_end": time(17),
                    "preferred_focus_periods": [],
                    "require_event_creation_approval": True,
                },
            )
            task_map = self._seed_tasks(user, day)
            result = self._run_trajectory(
                agent=agent,
                user=user,
                task_map=task_map,
                day=day,
                request_ids=request_ids,
            )
        finally:
            if request_ids:
                LLMCallAudit.objects.filter(request_id__in=request_ids).delete()
            user.delete()

        output_path = options.get("output")
        if output_path:
            self._write_report(output_path, result)
            self.stdout.write(f"Sanitized trajectory report: {output_path}")
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        self.stdout.write(
            self.style.SUCCESS(
                "Synthetic day trajectory completed: "
                f"{result['step_count']} steps, "
                f"{result['fresh_draft_count']} draft(s), "
                f"{result['hitl_pending_count']} pending approval interrupt(s), "
                "0 approvals."
            )
        )

    @staticmethod
    def _ensure_local_evaluation_database() -> None:
        database = settings.DATABASES["default"]
        settings_module = str(settings.SETTINGS_MODULE)
        if settings_module.endswith(".production"):
            raise CommandError("Synthetic day evaluation is disabled under production settings.")
        engine = str(database.get("ENGINE", ""))
        host = str(database.get("HOST", "")).strip().lower()
        database_name = str(database.get("NAME", "")).strip().lower()
        if any(
            marker in {"prod", "production", "live"}
            for marker in database_name.replace("-", "_").split("_")
        ):
            raise CommandError("Synthetic day evaluation refuses production-named databases.")
        if engine.endswith("sqlite3"):
            return
        if engine.endswith("postgresql") and host in {"", "localhost", "127.0.0.1", "::1"}:
            return
        raise CommandError(
            "Synthetic day evaluation requires a local SQLite or loopback PostgreSQL database."
        )

    @staticmethod
    def _seed_tasks(user: User, day: date) -> dict[str, Task]:
        local = ZoneInfo(TIMEZONE_NAME)
        task_specs = (
            ("inbox", "收件箱分拣", 45, TaskPriority.HIGH, time(11)),
            ("brief", "客户简报", 120, TaskPriority.URGENT, time(16)),
            ("report", "周报撰写", 90, TaskPriority.HIGH, time(17)),
            ("minutes", "会议纪要整理", 60, TaskPriority.MEDIUM, time(17, 30)),
            ("records", "客户资料整理", 60, TaskPriority.MEDIUM, time(17)),
            ("invoice", "账单核验", 30, TaskPriority.LOW, time(17)),
        )
        tasks: dict[str, Task] = {}
        for key, title, estimate, priority, deadline in task_specs:
            due_at = datetime.combine(day, deadline, tzinfo=local)
            tasks[key] = TaskService.create_task(
                CreateTaskCommand(
                    user=user,
                    title=title,
                    description="合成的单日评测任务。",
                    priority=priority,
                    due_at=due_at,
                    estimated_minutes=estimate,
                    source="evaluation",
                    origin="evaluation",
                )
            )
        return tasks

    @classmethod
    def _run_trajectory(
        cls,
        *,
        agent: Any,
        user: User,
        task_map: dict[str, Task],
        day: date,
        request_ids: list[str],
    ) -> dict[str, Any]:
        conversation_id = str(uuid4())
        history: list[Any] = []
        previous_slots: dict[str, list[tuple[datetime, datetime]]] = {}
        previous_plan_seen = False
        step_results: list[dict[str, Any]] = []
        all_tool_call_count = 0
        seen_tool_call_ids: set[str] = set()
        hitl_pending_count = 0
        created_plan_ids: set[str] = set()
        steps = trajectory_steps(day)
        for step in steps:
            anchor = step["anchor"]
            cls._apply_synthetic_mutation(
                step["mutation"],
                user=user,
                task_map=task_map,
                anchor=anchor,
            )
            before_ids = set(
                str(plan_id)
                for plan_id in SchedulePlan.objects.filter(user=user).values_list("pk", flat=True)
            )
            request_id = str(uuid4())
            request_ids.append(request_id)
            context = RuntimeContext(
                user_id=str(user.pk),
                request_id=request_id,
                timezone=TIMEZONE_NAME,
                locale=LOCALE,
                current_datetime=anchor,
                trigger_type="user_message",
                conversation_id=conversation_id,
                input_message=str(step["prompt"]),
                actor=user,
            )
            current_message = HumanMessage(
                content=str(step["prompt"]),
                additional_kwargs={
                    "run_anchor_datetime_utc": anchor.astimezone(UTC).isoformat(),
                },
            )
            history_length_before = len(history)
            started = perf_counter()
            result = agent.invoke(
                {"messages": [*history, current_message]},
                config={"configurable": {"thread_id": conversation_id}},
                context=context,
            )
            messages = result.get("messages", [])
            if not messages or not isinstance(messages[-1], AIMessage):
                raise CommandError(f"Trajectory step {step['id']} returned no final AI message")
            turn_messages = (
                messages[history_length_before:]
                if len(messages) >= history_length_before
                else messages
            )
            if len(messages) >= len(history):
                history = list(messages)
            else:
                history.extend([current_message, *messages])

            interrupts = result.get("__interrupt__", [])
            pending_names = _extract_interrupt_tool_names(interrupts, turn_messages)
            has_pending = bool(interrupts)
            hitl_pending_count += len(pending_names) if pending_names else int(has_pending)
            if has_pending:
                # The current operation was interrupted before execution. Add a truthful
                # synthetic tool observation so the next user turn cannot look like an
                # approval decision. Never call Command(resume=...) in this evaluator.
                tool_call_ids = {
                    str(call.get("id", ""))
                    for message in messages
                    if isinstance(message, AIMessage)
                    for call in message.tool_calls
                    if call.get("name") in pending_names
                }
                known_tool_messages = {
                    str(message.tool_call_id)
                    for message in history
                    if isinstance(message, ToolMessage)
                }
                for message in messages:
                    if not isinstance(message, AIMessage):
                        continue
                    for call in message.tool_calls:
                        call_id = str(call.get("id", ""))
                        if call_id in tool_call_ids and call_id not in known_tool_messages:
                            history.append(
                                ToolMessage(
                                    content=(
                                        "This synthetic evaluation did not approve the action. "
                                        "It remains unexecuted and requires explicit user approval."
                                    ),
                                    tool_call_id=call_id,
                                    name=str(call.get("name", "unknown_tool")),
                                    status="error",
                                )
                            )

            # SummarizationMiddleware can replace or shorten prior messages, so a
            # slice based on the previous history length may drop this turn's tool calls.
            # Scan the returned transcript and deduplicate by stable tool-call ID instead.
            tool_calls = cls._safe_tool_calls(messages, seen_tool_call_ids)
            all_tool_call_count += len(tool_calls)
            after_plans = list(SchedulePlan.objects.filter(user=user).order_by("created_at", "id"))
            fresh_plans = [plan for plan in after_plans if str(plan.pk) not in before_ids]
            created_plan_ids.update(str(plan.pk) for plan in fresh_plans)
            selected_plan = cls._select_draft(fresh_plans)
            plan_slots = (
                _plan_slots(selected_plan.items) if selected_plan is not None else previous_slots
            )
            delta = (
                compare_schedule_snapshots(previous_slots, plan_slots)
                if previous_plan_seen
                else {"moved_task_count": 0, "total_shift_minutes": 0}
            )
            if selected_plan is not None:
                previous_slots = plan_slots
                previous_plan_seen = True

            current_tasks = {
                str(task.pk): task
                for task in Task.objects.filter(user=user)
                if task.status in {TaskStatus.PENDING, TaskStatus.IN_PROGRESS}
            }
            preservation = cls._preservation_metrics(
                slots=plan_slots,
                tasks=current_tasks,
                day=day,
                events=EventService.list_events(
                    EventQuery(
                        user=user,
                        statuses=(
                            CalendarEventStatus.CONFIRMED,
                            CalendarEventStatus.TENTATIVE,
                        ),
                    )
                ),
            )
            final_message = messages[-1]
            response = str(final_message.content)
            step_results.append(
                {
                    "step_id": step["id"],
                    "anchor_local": anchor.isoformat(),
                    "fact_change": step["mutation"] or "initial_state",
                    "decision": cls._classify_decision(
                        response=response,
                        fresh_plan_count=len(fresh_plans),
                        hitl_pending=has_pending,
                    ),
                    "fresh_draft_count": len(fresh_plans),
                    "selected_draft_status": (
                        selected_plan.status if selected_plan is not None else None
                    ),
                    "tool_call_count": len(tool_calls),
                    "tool_names": sorted({call["name"] for call in tool_calls}),
                    "tool_error_count": sum(call["status"] == "error" for call in tool_calls),
                    "hitl_pending": has_pending,
                    "pending_approval_tool_names": pending_names,
                    "approved_action_count": 0,
                    "moved_task_count": delta["moved_task_count"],
                    "total_shift_minutes": delta["total_shift_minutes"],
                    **preservation,
                    "response_characters": len(response),
                    "duration_seconds": round(perf_counter() - started, 3),
                }
            )

        proposal_status_counts: dict[str, int] = {}
        for row in (
            ActionProposal.objects.filter(user=user)
            .values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        ):
            proposal_status_counts[str(row["status"])] = int(row["count"])

        return {
            "evaluation": "synthetic_whole_day_trajectory_v1",
            "evaluation_date": day.isoformat(),
            "timezone": TIMEZONE_NAME,
            "scenario_source": "embedded_synthetic_timeline",
            "production_data_used": False,
            "sealed_holdout_read": False,
            "approval_policy": "never_auto_approve",
            "step_count": len(step_results),
            "fresh_draft_count": len(created_plan_ids),
            "total_tool_call_count": all_tool_call_count,
            "hitl_pending_count": hitl_pending_count,
            "approved_action_count": 0,
            "total_moved_task_count": sum(int(step["moved_task_count"]) for step in step_results),
            "total_shift_minutes": sum(int(step["total_shift_minutes"]) for step in step_results),
            "action_proposal_status_counts": proposal_status_counts,
            "steps": step_results,
        }

    @staticmethod
    def _select_draft(plans: Sequence[SchedulePlan]) -> SchedulePlan | None:
        drafts = [plan for plan in plans if plan.status == SchedulePlanStatus.DRAFT]
        if not drafts:
            return None

        def score(plan: SchedulePlan) -> tuple[int, int]:
            placed = sum(
                1 for item in plan.items if item.get("task_id") and item.get("state") == "placed"
            )
            evidence: dict[str, object] = {}
            for item in plan.items:
                raw_evidence = item.get("evidence")
                if item.get("kind") == "plan_evidence" and isinstance(raw_evidence, dict):
                    evidence = raw_evidence
                    break
            validation_value = evidence.get("creation_validation", {})
            validation = validation_value if isinstance(validation_value, dict) else {}
            raw_reason_codes = validation.get("reason_codes", [])
            reason_codes = raw_reason_codes if isinstance(raw_reason_codes, list) else []
            hard_issues = sum(
                1
                for issue in reason_codes
                if str(issue).startswith(("deadline_", "overlap_", "outside_"))
            )
            return (placed, -hard_issues)

        return max(drafts, key=score)

    @staticmethod
    def _preservation_metrics(
        *,
        slots: dict[str, list[tuple[datetime, datetime]]],
        tasks: dict[str, Task],
        day: date,
        events: Sequence[CalendarEvent] = (),
    ) -> dict[str, Any]:
        timezone = ZoneInfo(TIMEZONE_NAME)
        work_start = time(9)
        work_end = time(17)
        deadline_checks = 0
        missed_deadlines = 0
        preference_checks = 0
        preference_violations = 0
        duration_checks = 0
        duration_mismatches = 0
        event_conflicts = 0
        for task_id, task in tasks.items():
            task_slots = slots.get(task_id)
            if task.due_at is not None:
                deadline_checks += 1
                if not task_slots or max(end for _, end in task_slots) > task.due_at:
                    missed_deadlines += 1
            if not task_slots:
                continue
            if task.estimated_minutes is not None:
                duration_checks += 1
                planned_minutes = sum(
                    round((end - start).total_seconds() / 60) for start, end in task_slots
                )
                if planned_minutes != task.estimated_minutes:
                    duration_mismatches += 1
            for start, end in task_slots:
                local_start = start.astimezone(timezone)
                local_end = end.astimezone(timezone)
                preference_checks += 1
                if (
                    local_start.date() != day
                    or local_end.date() != day
                    or local_start.time() < work_start
                    or local_end.time() > work_end
                ):
                    preference_violations += 1
                if any(start < event.end_at and end > event.start_at for event in events):
                    event_conflicts += 1
        return {
            "deadline_check_count": deadline_checks,
            "deadline_violation_count": missed_deadlines,
            "deadline_preservation_rate": (
                round((deadline_checks - missed_deadlines) / deadline_checks, 4)
                if deadline_checks
                else None
            ),
            "worktime_preference_check_count": preference_checks,
            "worktime_preference_violation_count": preference_violations,
            "worktime_preference_preserved": preference_violations == 0,
            "estimated_duration_check_count": duration_checks,
            "estimated_duration_mismatch_count": duration_mismatches,
            "estimated_duration_preservation_rate": (
                round((duration_checks - duration_mismatches) / duration_checks, 4)
                if duration_checks
                else None
            ),
            "event_conflict_count": event_conflicts,
            "event_schedule_preserved": event_conflicts == 0,
            "unplanned_active_task_count": sum(1 for task_id in tasks if task_id not in slots),
        }

    @staticmethod
    def _classify_decision(
        *,
        response: str,
        fresh_plan_count: int,
        hitl_pending: bool,
    ) -> str:
        if hitl_pending:
            return "approval_pause"
        if fresh_plan_count:
            return "replan"
        if any(token in response for token in ("？", "?", "请问", "需要你确认")):
            return "ask"
        if any(token in response for token in ("保持原安排", "无需调整", "保持不变", "不需要重排")):
            return "keep_stable"
        return "explain_without_new_draft"

    @staticmethod
    def _safe_tool_calls(
        messages: Sequence[Any],
        seen_call_ids: set[str],
    ) -> list[dict[str, str]]:
        statuses = {
            str(message.tool_call_id): str(message.status or "success")
            for message in messages
            if isinstance(message, ToolMessage)
        }
        calls: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, AIMessage):
                continue
            for call in message.tool_calls:
                call_id = str(call.get("id", ""))
                if call_id and call_id in seen_call_ids:
                    continue
                if call_id:
                    seen_call_ids.add(call_id)
                calls.append(
                    {
                        "name": str(call.get("name", "unknown_tool")),
                        "status": statuses.get(call_id, "pending"),
                    }
                )
        return calls

    @staticmethod
    def _apply_synthetic_mutation(
        mutation: str | None,
        *,
        user: User,
        task_map: dict[str, Task],
        anchor: datetime,
    ) -> None:
        if mutation is None:
            return
        if mutation == "complete_inbox":
            TaskService.complete_task(
                task_id=task_map["inbox"].pk,
                user=user,
                occurred_at=to_utc(anchor),
                origin="evaluation",
            )
        elif mutation == "extend_minutes":
            TaskService.update_task(
                UpdateTaskCommand(
                    user=user,
                    task_id=task_map["minutes"].pk,
                    changes={"estimated_minutes": 90},
                    expected_version=task_map["minutes"].version,
                    origin="evaluation",
                )
            )
            task_map["minutes"].refresh_from_db()
        elif mutation == "add_meeting":
            start_at = _local_anchor(anchor.astimezone(ZoneInfo(TIMEZONE_NAME)).date(), 13)
            EventService.create_event(
                CreateEventCommand(
                    user=user,
                    title="临时评测会议",
                    start_at=start_at,
                    end_at=start_at + timedelta(hours=1),
                    timezone=TIMEZONE_NAME,
                    source="local",
                    origin="evaluation",
                )
            )
        elif mutation == "cancel_records":
            TaskService.cancel_task(
                task_id=task_map["records"].pk,
                user=user,
                occurred_at=to_utc(anchor),
                origin="evaluation",
            )
        elif mutation == "add_urgent":
            due_at = _local_anchor(anchor.astimezone(ZoneInfo(TIMEZONE_NAME)).date(), 18)
            task_map["urgent"] = TaskService.create_task(
                CreateTaskCommand(
                    user=user,
                    title="紧急缺陷修复",
                    description="合成的临时紧急任务。",
                    priority=TaskPriority.URGENT,
                    due_at=due_at,
                    estimated_minutes=45,
                    source="evaluation",
                    origin="evaluation",
                )
            )
        else:
            raise ValueError(f"Unknown synthetic trajectory mutation: {mutation}")

    @staticmethod
    def _write_report(path: Path, report: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
