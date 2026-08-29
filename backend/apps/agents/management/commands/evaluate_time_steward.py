import hashlib
import json
import os
import re
from datetime import UTC, datetime, time
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError, CommandParser
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.configuration import get_agent_config
from apps.agents.context import RuntimeContext
from apps.agents.middleware import PROMPT_PATH
from apps.agents.model import build_chat_model
from apps.observability.models import LLMCallAudit
from apps.preferences.services import UserPreferenceService

EVAL_NOW = datetime(2026, 7, 17, 8, tzinfo=UTC)
EVAL_TIMEZONE = "Asia/Shanghai"
EVAL_LOCALE = "zh-CN"


class Command(BaseCommand):
    help = "Run the fixed Time Steward trajectory evaluation against a real configured model."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--model",
            help="Configured model alias; defaults to agent.default_model.",
        )
        parser.add_argument(
            "--case",
            action="append",
            dest="case_ids",
            help="Run only the selected case ID. May be repeated.",
        )
        parser.add_argument("--dataset", type=Path, help="Versioned evaluation dataset JSON path.")
        parser.add_argument(
            "--output", type=Path, help="Write a reproducible JSON report atomically."
        )
        parser.add_argument("--minimum-pass-rate", type=float, default=1.0)
        parser.add_argument(
            "--ablation",
            choices=("none", "temporal-context"),
            default="none",
            help="Disable one named Agent module for a controlled evaluation comparison.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        dataset_path = options.get("dataset") or self._default_dataset_path()
        cases = self._load_cases(dataset_path)
        selected = set(options.get("case_ids") or [])
        if selected:
            known = {case["id"] for case in cases}
            unknown = selected - known
            if unknown:
                raise CommandError(f"Unknown eval case(s): {', '.join(sorted(unknown))}")
            cases = [case for case in cases if case["id"] in selected]

        model_alias = options.get("model")
        ablation = str(options["ablation"])
        model = build_chat_model(model_alias)
        agent = build_time_steward_agent(
            model=model,
            temporal_context_enabled=ablation != "temporal-context",
        )
        failures: list[str] = []
        case_results: list[dict[str, Any]] = []
        evaluation_request_ids: list[str] = []

        # Agent tools may run in worker threads with separate database connections,
        # so an uncommitted fixture user is invisible to their FK validation. Use a
        # committed, uniquely named user and delete it (with all cascaded eval facts)
        # in finally instead of pretending one outer transaction covers every thread.
        user = User.objects.create_user(username=f"agent-eval-{uuid4().hex}")
        try:
            UserPreferenceService.update_for_user(
                user,
                {"timezone": EVAL_TIMEZONE, "locale": EVAL_LOCALE},
            )
            for case in cases:
                started = perf_counter()
                case_request_start = len(evaluation_request_ids)
                actual, final_response, tool_calls = self._run_case(
                    agent,
                    user,
                    case,
                    request_ids=evaluation_request_ids,
                )
                case_request_ids = evaluation_request_ids[case_request_start:]
                duration_seconds = perf_counter() - started
                required = set(case["required_tools"])
                allowed = set(case["allowed_tools"])
                forbidden = set(case["forbidden_tools"])
                missing = required - actual
                unexpected = actual - allowed
                forbidden_used = forbidden & actual
                forbidden_patterns = [
                    str(pattern) for pattern in case.get("forbidden_response_patterns", [])
                ]
                required_patterns = [
                    str(pattern) for pattern in case.get("required_response_patterns", [])
                ]
                forbidden_response_matches = [
                    pattern
                    for pattern in forbidden_patterns
                    if re.search(pattern, final_response, re.IGNORECASE)
                ]
                missing_response_patterns = [
                    pattern
                    for pattern in required_patterns
                    if not re.search(pattern, final_response, re.IGNORECASE)
                ]
                temporal_expectation_errors = self._temporal_expectation_errors(case, tool_calls)
                usage = self._usage_for_requests(case_request_ids)
                passed = not (
                    missing
                    or unexpected
                    or forbidden_used
                    or forbidden_response_matches
                    or missing_response_patterns
                    or temporal_expectation_errors
                )
                result = {
                    "id": case["id"],
                    "passed": passed,
                    "duration_seconds": round(duration_seconds, 4),
                    "actual_tools": sorted(actual),
                    "missing_tools": sorted(missing),
                    "unexpected_tools": sorted(unexpected),
                    "forbidden_tools_used": sorted(forbidden_used),
                    "forbidden_response_matches": forbidden_response_matches,
                    "missing_response_patterns": missing_response_patterns,
                    "temporal_expectation_errors": temporal_expectation_errors,
                    "temporal_expectation_count": len(case.get("expected_relative_specs", [])),
                    "response_sha256": hashlib.sha256(final_response.encode()).hexdigest(),
                    "response_characters": len(final_response),
                    "required_tool_recall": len(required & actual) / max(len(required), 1),
                    "allowed_tool_precision": len(actual & allowed) / max(len(actual), 1),
                    "required_tool_count": len(required),
                    "tool_call_count": len(tool_calls),
                    "successful_tool_call_count": sum(
                        call.get("succeeded") is True for call in tool_calls
                    ),
                    **usage,
                }
                case_results.append(result)
                self.stdout.write(json.dumps(result, ensure_ascii=False))
                if not passed:
                    failures.append(case["id"])
        finally:
            User.objects.filter(pk=user.pk).delete()
            if evaluation_request_ids:
                LLMCallAudit.objects.filter(request_id__in=evaluation_request_ids).delete()

        pass_rate = (len(cases) - len(failures)) / max(len(cases), 1)
        report = self._report(
            dataset_path=dataset_path,
            model_alias=model_alias,
            cases=case_results,
            pass_rate=pass_rate,
            ablation=ablation,
        )
        output_path = options.get("output")
        if output_path:
            self._write_report(output_path, report)
            self.stdout.write(f"Evaluation report: {output_path}")
        minimum_pass_rate = options["minimum_pass_rate"]
        if not 0 <= minimum_pass_rate <= 1:
            raise CommandError("--minimum-pass-rate must be between 0 and 1")
        security_failures = [
            str(result["id"])
            for result in case_results
            if result["forbidden_tools_used"] or result["forbidden_response_matches"]
        ]
        if security_failures or pass_rate < minimum_pass_rate:
            raise CommandError(f"Time Steward eval failed: {', '.join(failures)}")
        passed_count = len(cases) - len(failures)
        self.stdout.write(
            self.style.SUCCESS(
                "Time Steward eval completed: "
                f"{passed_count}/{len(cases)} case(s) passed"
            )
        )

    @staticmethod
    def _run_case(
        agent: Any,
        user: User,
        case: dict[str, Any],
        *,
        request_ids: list[str] | None = None,
    ) -> tuple[set[str], str, list[dict[str, Any]]]:
        conversation_id = str(uuid4())
        raw_turns = case.get("turns")
        turns = (
            raw_turns
            if isinstance(raw_turns, list)
            else [{"prompt": case["prompt"], "anchor_at": EVAL_NOW.isoformat()}]
        )
        history: list[Any] = []
        all_messages: list[Any] = []
        for turn in turns:
            if not isinstance(turn, dict) or not isinstance(turn.get("prompt"), str):
                raise CommandError(f"Eval case {case['id']} has a malformed turn")
            try:
                anchor_at = datetime.fromisoformat(
                    str(turn.get("anchor_at", EVAL_NOW.isoformat())).replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise CommandError(f"Eval case {case['id']} has an invalid turn anchor") from exc
            prompt = str(turn["prompt"])
            request_id = str(uuid4())
            if request_ids is not None:
                request_ids.append(request_id)
            context = RuntimeContext(
                user_id=str(user.pk),
                request_id=request_id,
                timezone=EVAL_TIMEZONE,
                locale=EVAL_LOCALE,
                current_datetime=anchor_at,
                trigger_type="user_message",
                conversation_id=conversation_id,
                input_message=prompt,
                read_only=False,
                actor=user,
            )
            current_message = HumanMessage(
                content=prompt,
                additional_kwargs={"run_anchor_datetime_utc": anchor_at.isoformat()},
            )
            result = agent.invoke(
                {"messages": [*history, current_message]},
                context=context,
            )
            messages = result.get("messages", [])
            if not messages or not isinstance(messages[-1], AIMessage):
                raise CommandError(f"Eval case {case['id']} did not produce a final AIMessage")
            new_messages = messages[len(history) :] if len(messages) > len(history) else messages
            all_messages.extend(new_messages)
            history = list(messages)
        actual_tools = {
            str(tool_call["name"])
            for message in all_messages
            if isinstance(message, AIMessage)
            for tool_call in message.tool_calls
        }
        tool_calls: list[dict[str, Any]] = []
        seen_tool_call_ids: set[str] = set()
        tool_statuses = {
            str(message.tool_call_id): message.status
            for message in all_messages
            if isinstance(message, ToolMessage)
        }
        for message in all_messages:
            if not isinstance(message, AIMessage):
                continue
            for tool_call in message.tool_calls:
                tool_call_id = str(tool_call.get("id", ""))
                if tool_call_id and tool_call_id in seen_tool_call_ids:
                    continue
                if tool_call_id:
                    seen_tool_call_ids.add(tool_call_id)
                tool_calls.append(
                    {
                        "id": tool_call_id,
                        "name": str(tool_call["name"]),
                        "args": dict(tool_call.get("args", {})),
                        "succeeded": tool_statuses.get(tool_call_id) != "error",
                    }
                )
        final_response = str(history[-1].content)
        return actual_tools, final_response, tool_calls

    @staticmethod
    def _usage_for_requests(request_ids: list[str]) -> dict[str, int | float | None]:
        rows = list(
            LLMCallAudit.objects.filter(
                request_id__in=request_ids,
                component="time_steward",
            ).values("status", "total_tokens")
        )
        completed = [row for row in rows if row["status"] == "completed"]
        token_rows = [
            int(row["total_tokens"]) for row in completed if row["total_tokens"] is not None
        ]
        return {
            "model_call_count": len(rows),
            "completed_model_call_count": len(completed),
            "total_tokens": sum(token_rows) if token_rows else None,
            "token_call_coverage": (
                round(len(token_rows) / len(completed), 4) if completed else None
            ),
        }

    @staticmethod
    def _temporal_expectation_errors(
        case: dict[str, Any], tool_calls: list[dict[str, Any]]
    ) -> list[str]:
        if "expected_relative_specs" not in case:
            return []
        expectations = case.get("expected_relative_specs", [])
        if not isinstance(expectations, list):
            return ["expected_relative_specs must be a list"]
        relative_creates: list[dict[str, Any]] = []
        for call in tool_calls:
            if call.get("name") != "mutate_events" or call.get("succeeded") is not True:
                continue
            operations = call.get("args", {}).get("operations", [])
            if not isinstance(operations, list):
                continue
            relative_creates.extend(
                operation
                for operation in operations
                if isinstance(operation, dict) and operation.get("action") == "create"
            )
        errors: list[str] = []
        if len(relative_creates) != len(expectations):
            errors.append(
                f"expected {len(expectations)} relative creates, got {len(relative_creates)}"
            )
            return errors
        for index, (operation, expectation) in enumerate(
            zip(relative_creates, expectations, strict=True)
        ):
            event_time = operation.get("time")
            if not isinstance(event_time, dict) or event_time.get("kind") != "relative":
                errors.append(f"relative create {index} omitted time.kind=relative")
                continue
            if event_time.get("start_at") is not None or event_time.get("end_at") is not None:
                errors.append(f"relative create {index} mixed in absolute time fields")
            if not isinstance(expectation, dict):
                errors.append(f"relative expectation {index} is malformed")
                continue
            for field in ("offset", "unit", "local_time", "source_text"):
                if field in expectation and not Command._temporal_value_matches(
                    field,
                    event_time.get(field),
                    expectation[field],
                ):
                    errors.append(
                        f"relative create {index} {field} mismatch: {event_time.get(field)!r}"
                    )
        return errors

    @staticmethod
    def _temporal_value_matches(field: str, actual: object, expected: object) -> bool:
        if field != "local_time":
            return actual == expected
        try:
            return time.fromisoformat(str(actual)) == time.fromisoformat(str(expected))
        except ValueError:
            return False

    @staticmethod
    def _default_dataset_path() -> Path:
        return Path(settings.BASE_DIR) / "tests" / "fixtures" / "time_steward_eval.json"

    @staticmethod
    def _load_cases(path: Path | None = None) -> list[dict[str, Any]]:
        path = path or Command._default_dataset_path()
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot load fixed eval set: {path}") from exc
        if not isinstance(value, list) or not value:
            raise CommandError("Fixed eval set must be a non-empty list")
        return value

    @staticmethod
    def _report(
        *,
        dataset_path: Path,
        model_alias: str | None,
        cases: list[dict[str, Any]],
        pass_rate: float,
        ablation: str,
    ) -> dict[str, Any]:
        definition = get_agent_config().selected_model(model_alias)
        durations = sorted(float(case["duration_seconds"]) for case in cases)
        p95_index = min(len(durations) - 1, int((len(durations) - 1) * 0.95))
        cases_with_required_tools = [case for case in cases if case["required_tool_count"]]
        cases_with_tool_calls = [case for case in cases if case["tool_call_count"]]
        temporal_cases = [case for case in cases if case["temporal_expectation_count"]]
        token_cases = [case for case in cases if case["total_tokens"] is not None]
        total_tokens = sum(int(case["total_tokens"]) for case in token_cases)
        return {
            "schema_version": "timeagent.agent-evaluation.v2",
            "created_at": datetime.now(UTC).isoformat(),
            "git_commit": os.getenv("GIT_COMMIT_SHA", "unknown"),
            "ablation": ablation,
            "dataset": {
                "path": str(dataset_path),
                "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            },
            "prompt_sha256": hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest(),
            "model": {
                "alias": model_alias or "default",
                "provider": definition.provider,
                "name": definition.model,
            },
            "summary": {
                "case_count": len(cases),
                "passed_count": sum(bool(case["passed"]) for case in cases),
                "pass_rate": pass_rate,
                "task_success_rate": pass_rate,
                "forbidden_tool_case_count": sum(
                    bool(case["forbidden_tools_used"]) for case in cases
                ),
                "required_tool_recall": Command._mean(
                    cases_with_required_tools,
                    "required_tool_recall",
                ),
                "allowed_tool_precision": Command._mean(
                    cases_with_tool_calls,
                    "allowed_tool_precision",
                ),
                "constraint_satisfaction_rate": (
                    round(
                        sum(not case["temporal_expectation_errors"] for case in temporal_cases)
                        / len(temporal_cases),
                        4,
                    )
                    if temporal_cases
                    else None
                ),
                "tool_calls_per_task": round(
                    sum(int(case["tool_call_count"]) for case in cases) / max(len(cases), 1),
                    4,
                ),
                "model_calls_per_task": round(
                    sum(int(case["model_call_count"]) for case in cases) / max(len(cases), 1),
                    4,
                ),
                "total_tokens": total_tokens if token_cases else None,
                "tokens_per_task": (
                    round(total_tokens / len(token_cases), 2) if token_cases else None
                ),
                "token_case_coverage": round(len(token_cases) / max(len(cases), 1), 4),
                "latency_p50_seconds": durations[len(durations) // 2],
                "latency_p95_seconds": durations[p95_index],
            },
            "cases": cases,
        }

    @staticmethod
    def _mean(cases: list[dict[str, Any]], field: str) -> float | None:
        if not cases:
            return None
        return round(sum(float(case[field]) for case in cases) / len(cases), 4)

    @staticmethod
    def _write_report(path: Path, report: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
