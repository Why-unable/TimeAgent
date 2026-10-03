from __future__ import annotations

import hashlib
import json
import math
import random
import re
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from datetime import time as local_time
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, TypedDict
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError, CommandParser
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_core.outputs import LLMResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command as GraphCommand

from apps.action_proposals.models import ActionProposal
from apps.action_proposals.services import ActionProposalService
from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.configuration import get_agent_config
from apps.agents.context import RuntimeContext
from apps.agents.middleware import resolve_request_policy
from apps.agents.model import build_chat_model, build_fallback_chat_models
from apps.agents.tool_discovery import ToolDiscoverySettings
from apps.agents.tools import TOOL_SPECS
from apps.conversations.services import (
    AgentRunService,
    ConversationService,
    StartRunCommand,
)
from apps.observability.models import LLMCallAudit
from apps.planning.models import SchedulePlan, SchedulePlanStatus
from apps.preferences.services import UserPreferenceService
from apps.tasks.services import CreateTaskCommand, TaskService

EVAL_TIMEZONE = "Asia/Shanghai"
_UUID_TEXT = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_CLARIFICATION_MARKERS = (
    "?",
    "\uff1f",
    "\u8bf7\u544a\u8bc9\u6211",
    "\u9700\u8981\u786e\u8ba4",
    "\u8fd8\u9700\u8981\u77e5\u9053",
    "\u4f60\u6307\u7684\u662f",
    "could you clarify",
    "please confirm",
    "which task",
)
_PRIVATE_ARGUMENT_KEYS = frozenset(
    {
        "task_id",
        "task_ids",
        "plan_id",
        "event_id",
        "reminder_id",
        "user_id",
        "interaction_id",
        "expected_version",
        "expected_versions",
    }
)
_SENSITIVE_ARGUMENT_KEYS = frozenset(
    {
        "email",
        "password",
        "token",
        "api_key",
        "authorization",
        "cookie",
        "access_token",
        "refresh_token",
    }
)


class SelectorUsageEvent(TypedDict):
    status: Literal["completed", "failed"]
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    duration_ms: int | None


class SelectorUsageCallback(BaseCallbackHandler):
    """Capture aggregate selector usage only; never store prompts or responses."""

    def __init__(self) -> None:
        self._started_at: dict[str, float] = {}
        self._events: list[SelectorUsageEvent] = []
        self._lock = threading.Lock()

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        del serialized, messages, kwargs
        with self._lock:
            self._started_at[str(run_id)] = perf_counter()

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        del serialized, prompts, kwargs
        with self._lock:
            self._started_at[str(run_id)] = perf_counter()

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        del kwargs
        usage = self._usage(response)
        with self._lock:
            started_at = self._started_at.pop(str(run_id), None)
            self._events.append(
                {
                    "status": "completed",
                    "input_tokens": usage[0],
                    "output_tokens": usage[1],
                    "total_tokens": usage[2],
                    "duration_ms": (
                        max(0, round((perf_counter() - started_at) * 1000))
                        if started_at is not None
                        else None
                    ),
                }
            )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        del error, kwargs
        with self._lock:
            started_at = self._started_at.pop(str(run_id), None)
            self._events.append(
                {
                    "status": "failed",
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "duration_ms": (
                        max(0, round((perf_counter() - started_at) * 1000))
                        if started_at is not None
                        else None
                    ),
                }
            )

    @staticmethod
    def _usage(response: LLMResult) -> tuple[int | None, int | None, int | None]:
        input_tokens = output_tokens = total_tokens = 0
        found_message_usage = False
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                message_usage = getattr(message, "usage_metadata", None)
                if not isinstance(message_usage, dict):
                    continue
                input_tokens += int(message_usage.get("input_tokens") or 0)
                output_tokens += int(message_usage.get("output_tokens") or 0)
                total_tokens += int(message_usage.get("total_tokens") or 0)
                found_message_usage = True
        if found_message_usage:
            return input_tokens, output_tokens, total_tokens or input_tokens + output_tokens

        raw_usage = response.llm_output or {}
        raw_usage = raw_usage.get("token_usage") or raw_usage.get("usage") or raw_usage
        if isinstance(raw_usage, dict):
            raw_input = raw_usage.get("prompt_tokens", raw_usage.get("input_tokens"))
            raw_output = raw_usage.get("completion_tokens", raw_usage.get("output_tokens"))
            raw_total = raw_usage.get("total_tokens")
            if isinstance(raw_input, int | float) and isinstance(raw_output, int | float):
                return (
                    int(raw_input),
                    int(raw_output),
                    int(raw_total)
                    if isinstance(raw_total, int | float)
                    else int(raw_input) + int(raw_output),
                )
        return None, None, None

    def snapshot_index(self) -> int:
        with self._lock:
            return len(self._events)

    def metrics_since(self, start_index: int) -> dict[str, Any]:
        with self._lock:
            events = list(self._events[start_index:])
        completed = [event for event in events if event["status"] == "completed"]
        durations = [event["duration_ms"] for event in events if event["duration_ms"] is not None]
        token_complete: list[tuple[int, int, int]] = []
        for event in completed:
            input_tokens = event["input_tokens"]
            output_tokens = event["output_tokens"]
            total_tokens = event["total_tokens"]
            if input_tokens is not None and output_tokens is not None and total_tokens is not None:
                token_complete.append((input_tokens, output_tokens, total_tokens))
        return {
            "call_count": len(events),
            "completed_call_count": len(completed),
            "failed_call_count": len(events) - len(completed),
            "input_tokens": (
                sum(tokens[0] for tokens in token_complete)
                if token_complete and len(token_complete) == len(events)
                else (0 if not events else None)
            ),
            "output_tokens": (
                sum(tokens[1] for tokens in token_complete)
                if token_complete and len(token_complete) == len(events)
                else (0 if not events else None)
            ),
            "total_tokens": (
                sum(tokens[2] for tokens in token_complete)
                if token_complete and len(token_complete) == len(events)
                else (0 if not events else None)
            ),
            "token_coverage": round(len(token_complete) / len(events), 4) if events else 1.0,
            "latency_ms_total": sum(durations),
            "latency_ms_mean": round(sum(durations) / len(durations), 2) if durations else None,
            "latency_ms_p50": _percentile(durations, 0.50),
            "latency_ms_p95": _percentile(durations, 0.95),
        }


class Command(BaseCommand):
    help = "Compare regex, LLM selector, BM25, and retrieval-plus-selector tool discovery."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dataset", type=Path)
        parser.add_argument("--case", action="append", dest="case_ids")
        parser.add_argument("--repeats", type=int, default=3)
        parser.add_argument("--model", help="Configured primary model alias.")
        parser.add_argument("--selector-model", help="Configured model alias used by B and D.")
        parser.add_argument("--seed", type=int, default=20261002)
        parser.add_argument("--output", type=Path)
        parser.add_argument("--blind-output", type=Path)
        parser.add_argument("--model-input-usd-per-million", type=float)
        parser.add_argument("--model-output-usd-per-million", type=float)
        parser.add_argument("--selector-input-usd-per-million", type=float)
        parser.add_argument("--selector-output-usd-per-million", type=float)

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        repeats = int(options["repeats"])
        if not 1 <= repeats <= 5:
            raise CommandError("--repeats must be between 1 and 5")
        dataset_path = options.get("dataset") or self._default_dataset_path()
        dataset = self._load_dataset(dataset_path)
        cases = list(dataset["scenarios"])
        requested = set(options.get("case_ids") or [])
        if requested:
            known = {str(case["id"]) for case in cases}
            unknown = requested - known
            if unknown:
                raise CommandError(f"Unknown case ID(s): {', '.join(sorted(unknown))}")
            cases = [case for case in cases if str(case["id"]) in requested]
        if not cases:
            raise CommandError("No discovery cases selected")

        config = get_agent_config()
        model_alias = options.get("model") or config.agent.default_model
        main_model = config.selected_model(model_alias)
        selector_alias = (
            options.get("selector_model") or config.tool_discovery.selector_model or model_alias
        )
        selector_model = config.selected_model(selector_alias)
        price_options = self._prices(options, str(model_alias), str(selector_alias))
        variants, label_by_variant = self._variants(selector_alias)
        selector_callbacks = {
            variant["id"]: SelectorUsageCallback()
            for variant in variants
            if variant["settings"].strategy in {"llm_selector", "retrieval_plus_llm"}
        }
        agents: dict[str, Any] = {}
        for variant in variants:
            settings_value: ToolDiscoverySettings = variant["settings"]
            agents[variant["id"]] = build_time_steward_agent(
                model=build_chat_model(model_alias),
                fallback_models=build_fallback_chat_models(),
                checkpointer=InMemorySaver(),
                store=InMemoryStore(),
                compact_planning_surface=False,
                discovery_settings=settings_value,
                selector_callbacks=(
                    [selector_callbacks[variant["id"]]]
                    if variant["id"] in selector_callbacks
                    else None
                ),
            )

        raw_results: list[dict[str, Any]] = []
        blind_trajectories: list[dict[str, Any]] = []
        scheduled_order: list[dict[str, Any]] = []
        for case_index, case in enumerate(cases):
            for repeat_index in range(1, repeats + 1):
                order = list(variants)
                random.Random(int(options["seed"]) + case_index * 101 + repeat_index).shuffle(order)
                scheduled_order.append(
                    {
                        "case_id": str(case["id"]),
                        "repeat": repeat_index,
                        "variant_order": [variant["id"] for variant in order],
                    }
                )
                for variant in order:
                    callback = selector_callbacks.get(variant["id"])
                    selector_start = callback.snapshot_index() if callback is not None else 0
                    row_started = perf_counter()
                    invocation_started: float | None = None
                    request_ids: list[str] = []
                    hard_policy_trace: list[dict[str, Any]] = []
                    user: User | None = None
                    try:
                        user, task_by_title = self._seed_trial(case, dataset)
                        invocation_started = perf_counter()
                        (
                            result,
                            request_ids,
                            pending_names,
                            proposal_ids,
                            requested_names,
                            hard_policy_trace,
                        ) = self._invoke_trial(
                            agent=agents[variant["id"]],
                            user=user,
                            case=case,
                            dataset=dataset,
                            request_ids=request_ids,
                            hard_policy_trace=hard_policy_trace,
                            approve_expected=case.get("success_mode") == "hitl_roundtrip",
                        )
                        wall_seconds = perf_counter() - invocation_started
                        messages = result.get("messages", []) if isinstance(result, dict) else []
                        final_response = self._final_response(messages)
                        trace = self._tool_trace(messages)
                        usage = self._usage_for_requests(request_ids)
                        selector_usage = (
                            callback.metrics_since(selector_start)
                            if callback is not None
                            else self._empty_selector_metrics()
                        )
                        hitl_usage = self._hitl_metrics(proposal_ids)
                        row = self._trial_metrics(
                            case=case,
                            variant=variant,
                            trace=trace,
                            final_response=final_response,
                            user=user,
                            task_by_title=task_by_title,
                            pending_names=pending_names,
                            requested_names=requested_names,
                            hard_policy_trace=hard_policy_trace,
                            hitl_usage=hitl_usage,
                            model_usage=usage,
                            selector_usage=selector_usage,
                            wall_seconds=wall_seconds,
                            price_options=price_options,
                            model_alias=str(model_alias),
                            model_name=main_model.model,
                            selector_alias=str(selector_alias),
                            selector_model_name=selector_model.model,
                        )
                        row["repeat"] = repeat_index
                        row["blind_condition_id"] = label_by_variant[variant["id"]]
                        row["fixture_hash"] = self._case_hash(case)
                        raw_results.append(row)
                        trajectory = {
                            "case_id": str(case["id"]),
                            "repeat": repeat_index,
                            "condition_id": label_by_variant[variant["id"]],
                            "trajectory_complete": True,
                            "turns": [str(item["prompt"]) for item in case["turns"]],
                            "tool_calls": [
                                {
                                    "name": item["name"],
                                    "status": item["status"],
                                    "arguments": item["safe_arguments"],
                                }
                                for item in trace
                            ],
                            "model_visible_tools": usage["visible_tool_names"],
                            "pending_approval_tools": pending_names,
                            "approval_requested_tools": requested_names,
                            "hitl_completion": hitl_usage["completed_count"],
                            "final_response": _UUID_TEXT.sub("<synthetic-id>", final_response),
                        }
                        blind_trajectories.append(trajectory)
                        self.stdout.write(
                            json.dumps(
                                {
                                    "case_id": row["case_id"],
                                    "repeat": repeat_index,
                                    "variant": variant["id"],
                                    "task_success": row["task_success"],
                                    "tool_call_count": row["tool_call_count"],
                                    "latency_seconds": row["latency_seconds"],
                                },
                                ensure_ascii=False,
                            )
                        )
                    except Exception as exc:
                        wall_seconds = perf_counter() - (
                            invocation_started if invocation_started is not None else row_started
                        )
                        usage = self._usage_for_requests(request_ids)
                        selector_usage = (
                            callback.metrics_since(selector_start)
                            if callback is not None
                            else self._empty_selector_metrics()
                        )
                        row = {
                            "case_id": str(case["id"]),
                            "repeat": repeat_index,
                            "variant": variant["id"],
                            "blind_condition_id": label_by_variant[variant["id"]],
                            "success_mode": str(
                                case.get("success_mode", "required_tools_succeeded")
                            ),
                            "required_tools": sorted(
                                str(name) for name in case.get("required_tools", [])
                            ),
                            "allowed_tools": sorted(
                                str(name) for name in case.get("allowed_tools", [])
                            ),
                            "forbidden_tools": sorted(
                                str(name) for name in case.get("forbidden_tools", [])
                            ),
                            "task_success": False,
                            "error_type": type(exc).__name__,
                            "trajectory_complete": False,
                            "latency_seconds": round(wall_seconds, 4),
                            "model_call_count": usage["model_call_count"],
                            "model_input_tokens": usage["input_tokens"],
                            "model_output_tokens": usage["output_tokens"],
                            "model_total_tokens": usage["total_tokens"],
                            "model_token_coverage": usage["token_coverage"],
                            "tool_call_count": None,
                            "selector_call_count": selector_usage["call_count"],
                            "selector_input_tokens": selector_usage["input_tokens"],
                            "selector_output_tokens": selector_usage["output_tokens"],
                            "selector_total_tokens": selector_usage["total_tokens"],
                            "selector_token_coverage": selector_usage["token_coverage"],
                            "selector_latency_ms_p50": selector_usage["latency_ms_p50"],
                            "selector_latency_ms_p95": selector_usage["latency_ms_p95"],
                            "hard_allowed_tool_count_mean": round(
                                sum(int(item["tool_count"]) for item in hard_policy_trace)
                                / len(hard_policy_trace),
                                2,
                            )
                            if hard_policy_trace
                            else None,
                            "hard_allowed_tool_count_by_turn": [
                                int(item["tool_count"]) for item in hard_policy_trace
                            ],
                            "hard_allowed_tool_names_by_turn": [
                                item["tool_names"] for item in hard_policy_trace
                            ],
                            "mean_visible_tools": usage["mean_visible_tools"],
                            "visible_tool_names": usage["visible_tool_names"],
                            "selected_tool_recall": (
                                round(
                                    len(
                                        set(
                                            str(name) for name in case.get("required_tools", [])
                                        ).intersection(usage["visible_tool_names"])
                                    )
                                    / len(case.get("required_tools", [])),
                                    4,
                                )
                                if case.get("required_tools")
                                else None
                            ),
                            "selected_tool_precision": (
                                round(
                                    len(
                                        set(usage["visible_tool_names"]).intersection(
                                            str(name) for name in case.get("allowed_tools", [])
                                        )
                                    )
                                    / len(usage["visible_tool_names"]),
                                    4,
                                )
                                if usage["visible_tool_names"]
                                else None
                            ),
                            "required_tool_recall": (0.0 if case.get("required_tools") else None),
                            "model_names": usage["model_names"],
                            "main_model_alias": str(model_alias),
                            "selector_model_alias": str(selector_alias)
                            if selector_usage["call_count"]
                            else None,
                            "estimated_cost_usd": None,
                            "fixture_hash": self._case_hash(case),
                        }
                        if isinstance(exc, AssertionError):
                            safe_message = str(exc)
                            if (
                                safe_message == "Invalid usage: tools must be non-empty"
                                or re.fullmatch(
                                    r"Expected dict response, got <class '[A-Za-z0-9_.]+'>",
                                    safe_message,
                                )
                            ):
                                row["safe_error_message"] = safe_message
                        raw_results.append(row)
                        blind_trajectories.append(
                            {
                                "case_id": row["case_id"],
                                "repeat": repeat_index,
                                "condition_id": row["blind_condition_id"],
                                "trajectory_complete": False,
                                "turns": [str(item["prompt"]) for item in case["turns"]],
                                "tool_calls": [],
                                "final_response": "",
                                "run_error_type": type(exc).__name__,
                            }
                        )
                        self.stderr.write(
                            f"Trial failed for {case['id']} / {variant['id']}: {type(exc).__name__}"
                        )
                    finally:
                        if user is not None:
                            User.objects.filter(pk=user.pk).delete()
                        if request_ids:
                            LLMCallAudit.objects.filter(request_id__in=request_ids).delete()

        summaries = self._summaries(raw_results, variants)
        report = {
            "experiment": "timeagent-tool-discovery-evolution-2026",
            "dataset_path": str(dataset_path),
            "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "scenario_count": len(cases),
            "repeats_per_scenario": repeats,
            "trial_count": len(raw_results),
            "evaluation_seed": int(options["seed"]),
            "fixture_anchor_at": dataset["anchor_at"],
            "timezone": dataset["timezone"],
            "main_model": {
                "alias": str(model_alias),
                "provider": main_model.provider,
                "name": main_model.model,
                "temperature": main_model.temperature,
                "provider_max_retries": main_model.provider_max_retries,
                "middleware_retries": config.middleware.model_retry_limit,
                "configured_timeout_seconds": main_model.timeout_seconds,
            },
            "selector_model": {
                "alias": str(selector_alias),
                "provider": selector_model.provider,
                "name": selector_model.model,
                "temperature": selector_model.temperature,
                "provider_max_retries": selector_model.provider_max_retries,
                "configured_timeout_seconds": selector_model.timeout_seconds,
            },
            "model_prices_usd_per_million_tokens": price_options,
            "variant_order": scheduled_order,
            "summaries": summaries,
            "raw_results": raw_results,
        }
        output_path = options.get("output") or self._default_output_path()
        self._write_json(output_path, report)
        blind_path = options.get("blind_output") or self._default_blind_output_path()
        blind_document = {
            "experiment": "timeagent-tool-discovery-blind-trajectories-2026",
            "dataset_sha256": report["dataset_sha256"],
            "note": "Conditions are anonymized. No model reasoning is included.",
            "trajectories": blind_trajectories,
        }
        self._write_json(blind_path, blind_document)
        self.stdout.write(f"Raw metrics: {output_path}")
        self.stdout.write(f"Blind trajectories: {blind_path}")

    @staticmethod
    def _default_dataset_path() -> Path:
        return Path(settings.BASE_DIR) / "tests" / "fixtures" / "tool_discovery_eval.json"

    @staticmethod
    def _default_output_path() -> Path:
        return (
            Path(settings.BASE_DIR).parent
            / "docs"
            / "experiments"
            / "artifacts"
            / "tool-discovery-evolution-2026-raw.json"
        )

    @staticmethod
    def _default_blind_output_path() -> Path:
        return (
            Path(settings.BASE_DIR).parent
            / "docs"
            / "experiments"
            / "artifacts"
            / "tool-discovery-evolution-2026-blind-trajectories.json"
        )

    @staticmethod
    def _load_dataset(path: Path) -> dict[str, Any]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot read discovery dataset: {path}") from exc
        if not isinstance(document, dict) or not isinstance(document.get("scenarios"), list):
            raise CommandError("Discovery dataset must contain a scenarios list")
        if not document["scenarios"]:
            raise CommandError("Discovery dataset contains no scenarios")
        return document

    @staticmethod
    def _variants(selector_alias: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
        definitions: list[tuple[str, ToolDiscoverySettings]] = [
            ("A_regex_pack", ToolDiscoverySettings(strategy="regex_pack")),
            *[
                (
                    f"B_llm_selector_{limit}",
                    ToolDiscoverySettings(
                        strategy="llm_selector",
                        selector_max_tools=limit,
                        selector_model_alias=selector_alias,
                    ),
                )
                for limit in (4, 6, 8)
            ],
            *[
                (
                    f"C_lexical_top_{limit}",
                    ToolDiscoverySettings(strategy="lexical_retrieval", lexical_top_k=limit),
                )
                for limit in (4, 6, 8, 10)
            ],
            *[
                (
                    f"D_retrieval_{candidate_top_k}_selector_{selector_top_k}",
                    ToolDiscoverySettings(
                        strategy="retrieval_plus_llm",
                        candidate_top_k=candidate_top_k,
                        selector_max_tools=selector_top_k,
                        selector_model_alias=selector_alias,
                    ),
                )
                for candidate_top_k in (8, 10)
                for selector_top_k in (4, 6)
            ],
        ]
        variants = [
            {"id": variant_id, "settings": settings_value}
            for variant_id, settings_value in definitions
        ]
        labels = [f"condition_{index:02d}" for index in range(1, len(variants) + 1)]
        random.Random(7032026).shuffle(labels)
        variant_ids = [variant_id for variant_id, _ in definitions]
        return variants, dict(zip(variant_ids, labels, strict=True))

    @staticmethod
    def _seed_trial(case: dict[str, Any], dataset: dict[str, Any]) -> tuple[User, dict[str, Any]]:
        user = User.objects.create_user(username=f"tool-discovery-eval-{uuid4().hex}")
        timezone_name = str(dataset.get("timezone", EVAL_TIMEZONE))
        UserPreferenceService.update_for_user(
            user,
            {
                "timezone": timezone_name,
                "locale": "zh-CN",
                "workday_start": local_time.fromisoformat(str(dataset["workday_start"])),
                "workday_end": local_time.fromisoformat(str(dataset["workday_end"])),
            },
        )
        due_at = datetime(2026, 10, 7, 15, tzinfo=UTC)
        task_by_title: dict[str, Any] = {}
        for title in case.get("seed_tasks", []):
            task_by_title[str(title)] = TaskService.create_task(
                CreateTaskCommand(
                    user=user,
                    title=str(title),
                    description="Synthetic tool discovery evaluation task",
                    estimated_minutes=60,
                    due_at=due_at,
                    source="evaluation",
                    origin="tool_discovery_evaluation",
                )
            )
        return user, task_by_title

    def _invoke_trial(
        self,
        *,
        agent: Any,
        user: User,
        case: dict[str, Any],
        dataset: dict[str, Any],
        request_ids: list[str],
        hard_policy_trace: list[dict[str, Any]],
        approve_expected: bool,
    ) -> tuple[dict[str, Any], list[str], list[str], list[str], list[str], list[dict[str, Any]]]:
        turns = case.get("turns")
        if not isinstance(turns, list) or not turns:
            raise CommandError(f"Case {case.get('id')} needs at least one turn")
        timezone_name = str(dataset.get("timezone", EVAL_TIMEZONE))
        anchor = self._datetime(str(dataset["anchor_at"]))
        conversation = ConversationService.create(user=user)
        first_prompt = str(turns[0]["prompt"])
        first_request_id = str(uuid4())
        run = AgentRunService.start(
            StartRunCommand(
                conversation=conversation,
                operation_id=uuid4(),
                request_id=first_request_id,
                message=first_prompt,
                anchor_at=anchor,
                anchor_timezone=timezone_name,
            )
        )
        run = AgentRunService.mark_running(run)
        request_ids.append(first_request_id)
        thread_id = str(conversation.pk)
        run_config = {"configurable": {"thread_id": thread_id}}
        last_context: RuntimeContext | None = None
        result: dict[str, Any] = {}
        pending_names: list[str] = []
        requested_names: list[str] = []
        proposal_ids: list[str] = []
        for turn in turns:
            if not isinstance(turn, dict) or not isinstance(turn.get("prompt"), str):
                raise CommandError(f"Case {case.get('id')} contains an invalid turn")
            prompt = str(turn["prompt"])
            current_anchor = self._datetime(str(turn.get("anchor_at", anchor.isoformat())))
            request_id = str(uuid4())
            request_ids.append(request_id)
            last_context = RuntimeContext(
                user_id=str(user.pk),
                request_id=request_id,
                timezone=timezone_name,
                locale="zh-CN",
                current_datetime=current_anchor,
                trigger_type="user_message",
                conversation_id=str(conversation.pk),
                agent_run_id=str(run.pk),
                input_message=prompt,
                actor=user,
            )
            policy = resolve_request_policy(last_context)
            hard_policy_trace.append(
                {
                    "tool_count": len(policy.hard_allowed_tools),
                    "tool_names": sorted(policy.hard_allowed_tools),
                }
            )
            result = agent.invoke(
                {
                    "messages": [
                        HumanMessage(
                            content=prompt,
                            additional_kwargs={
                                "run_anchor_datetime_utc": current_anchor.isoformat()
                            },
                        )
                    ]
                },
                config=run_config,
                context=last_context,
            )
            raw_interrupts = result.get("__interrupt__", [])
            if not raw_interrupts:
                continue
            names = self._interrupt_tool_names(raw_interrupts)
            pending_names = sorted(set(pending_names).union(names))
            requested_names = sorted(set(requested_names).union(names))
            interrupt_values = [getattr(item, "value", None) for item in raw_interrupts]
            proposals = [
                proposal
                for value in interrupt_values
                if isinstance(value, dict)
                for proposal in ActionProposalService.create_from_interrupt(
                    run=run,
                    interrupt_value=value,
                )
            ]
            proposal_ids.extend(str(proposal.pk) for proposal in proposals)
            approved_names = set(str(name) for name in case.get("approved_tools", []))
            proposal_names = {proposal.action_type for proposal in proposals}
            if not approve_expected or not proposals or not proposal_names.issubset(approved_names):
                AgentRunService.wait_for_approval(run)
                break
            for proposal in proposals:
                decision = ActionProposalService.decide(
                    user=user,
                    proposal_id=proposal.pk,
                    expected_version=proposal.version,
                    decision="approve",
                    decision_idempotency_key=uuid4(),
                )
                if not decision.resume_ready:
                    raise CommandError("Synthetic HITL approval was not ready to resume")
            resume_payload = ActionProposalService.resume_payload(run.pk)
            ActionProposalService.mark_resumed(run.pk)
            if last_context is None:
                raise CommandError("HITL resumed without a RuntimeContext")
            result = agent.invoke(
                GraphCommand(resume=resume_payload),
                config=run_config,
                context=last_context,
            )
            pending_names = []
        final_response = self._final_response(result.get("messages", []))
        if not pending_names:
            AgentRunService.complete(run, final_response)
        return (
            result,
            request_ids,
            pending_names,
            proposal_ids,
            requested_names,
            hard_policy_trace,
        )

    def _trial_metrics(
        self,
        *,
        case: dict[str, Any],
        variant: dict[str, Any],
        trace: list[dict[str, Any]],
        final_response: str,
        user: User,
        task_by_title: dict[str, Any],
        pending_names: list[str],
        requested_names: list[str],
        hard_policy_trace: list[dict[str, Any]],
        hitl_usage: dict[str, int | float | None],
        model_usage: dict[str, Any],
        selector_usage: dict[str, Any],
        wall_seconds: float,
        price_options: dict[str, float | None],
        model_alias: str,
        model_name: str,
        selector_alias: str,
        selector_model_name: str,
    ) -> dict[str, Any]:
        required = set(str(name) for name in case.get("required_tools", []))
        allowed = set(str(name) for name in case.get("allowed_tools", []))
        forbidden = set(str(name) for name in case.get("forbidden_tools", []))
        actual_names = {str(call["name"]) for call in trace}
        visible_names = set(str(name) for name in model_usage.get("visible_tool_names", []))
        successful_names = {str(call["name"]) for call in trace if call["status"] == "success"}
        missing = required - successful_names
        unexpected = actual_names - allowed
        forbidden_used = actual_names.intersection(forbidden)
        mismatches = [call for call in trace if call.get("error_code") == "tool_surface_mismatch"]
        unauthorized = [call for call in trace if call.get("error_code") == "tool_not_authorized"]
        failed_calls = [call for call in trace if call["status"] == "error"]
        write_calls = [
            call
            for call in trace
            if call["name"] in TOOL_SPECS
            and TOOL_SPECS[call["name"]].effect in {"draft", "business_write"}
        ]
        plan_count = SchedulePlan.objects.filter(user=user).count()
        duplicate_drafts = max(
            0,
            sum(call["name"] == "propose_schedule_plan" for call in trace) - 1,
        )
        mode = str(case.get("success_mode", "required_tools_succeeded"))
        success = not missing and not unexpected and not forbidden_used
        if mode == "plan_draft":
            success = success and plan_count > 0 and "propose_schedule_plan" in successful_names
        elif mode == "exact_plan_time":
            success = success and self._plan_has_exact_local_time(
                user=user,
                task_by_title=task_by_title,
                task_title=str(case.get("expected_task_title", "")),
                local_time_value=str(case.get("expected_local_time", "")),
                timezone_name=EVAL_TIMEZONE,
            )
        elif mode == "hitl_roundtrip":
            expected_approved = set(str(name) for name in case.get("approved_tools", []))
            completion_rate = hitl_usage.get("completion_rate")
            success = (
                success
                and expected_approved.issubset(successful_names)
                and not pending_names
                and completion_rate == 1.0
            )
        elif mode == "safe_no_write":
            success = success and not write_calls
        elif mode == "no_tool_calls":
            success = success and not trace and not pending_names
        clarification = self._looks_like_clarification(final_response)
        input_tokens = model_usage.get("input_tokens")
        output_tokens = model_usage.get("output_tokens")
        selector_input = selector_usage.get("input_tokens")
        selector_output = selector_usage.get("output_tokens")
        total_tokens = (
            int(model_usage["total_tokens"]) + int(selector_usage["total_tokens"])
            if isinstance(model_usage.get("total_tokens"), int)
            and isinstance(selector_usage.get("total_tokens"), int)
            else None
        )
        estimated_cost = self._estimated_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            selector_input_tokens=selector_input,
            selector_output_tokens=selector_output,
            prices=price_options,
        )
        if (
            (selector_usage.get("call_count") and selector_usage.get("token_coverage") != 1.0)
            or model_usage.get("token_coverage") != 1.0
            or set(model_usage.get("model_names", [])) - {model_name}
        ):
            estimated_cost = None
        return {
            "case_id": str(case["id"]),
            "variant": str(variant["id"]),
            "strategy": variant["settings"].strategy,
            "parameters": {
                "lexical_top_k": variant["settings"].lexical_top_k,
                "candidate_top_k": variant["settings"].candidate_top_k,
                "selector_max_tools": variant["settings"].selector_max_tools,
            },
            "task_success": bool(success),
            "success_mode": mode,
            "trajectory_complete": True,
            "required_tools": sorted(required),
            "hard_allowed_tool_count_mean": round(
                sum(int(item["tool_count"]) for item in hard_policy_trace)
                / max(len(hard_policy_trace), 1),
                2,
            ),
            "hard_allowed_tool_count_by_turn": [
                int(item["tool_count"]) for item in hard_policy_trace
            ],
            "hard_allowed_tool_names_by_turn": [item["tool_names"] for item in hard_policy_trace],
            "hard_allowed_tool_names_union": sorted(
                {name for item in hard_policy_trace for name in item["tool_names"]}
            ),
            "selected_tool_recall": (
                round(len(required.intersection(visible_names)) / len(required), 4)
                if required
                else None
            ),
            "selected_tool_precision": (
                round(len(visible_names.intersection(allowed)) / len(visible_names), 4)
                if visible_names
                else None
            ),
            "successful_required_tools": sorted(required.intersection(successful_names)),
            "missing_required_tools": sorted(missing),
            "allowed_tool_precision": (
                round(len(actual_names.intersection(allowed)) / len(actual_names), 4)
                if actual_names
                else None
            ),
            "required_tool_recall": (
                round(len(required.intersection(successful_names)) / len(required), 4)
                if required
                else None
            ),
            "wrong_tool_rate": round(len(unexpected) / max(len(actual_names), 1), 4),
            "wrong_tool_calls": sorted(unexpected),
            "forbidden_tool_call_count": len(forbidden_used),
            "forbidden_tool_call_rate": 1.0 if forbidden_used else 0.0,
            "tool_surface_mismatch_count": len(mismatches),
            "tool_surface_mismatch_rate": round(len(mismatches) / max(len(trace), 1), 4),
            "unauthorized_tool_call_count": len(unauthorized),
            "failed_tool_call_count": len(failed_calls),
            "clarification_requested": clarification,
            "agent_step_count": int(model_usage.get("model_call_count") or 0),
            "model_call_count": int(model_usage.get("model_call_count") or 0),
            "tool_call_count": len(trace),
            "selector_call_count": int(selector_usage.get("call_count") or 0),
            "selector_latency_ms_total": int(selector_usage.get("latency_ms_total") or 0),
            "selector_latency_ms_mean": selector_usage.get("latency_ms_mean"),
            "selector_latency_ms_p50": selector_usage.get("latency_ms_p50"),
            "selector_latency_ms_p95": selector_usage.get("latency_ms_p95"),
            "mean_visible_tools": model_usage.get("mean_visible_tools"),
            "visible_tool_count_mean": model_usage.get("mean_visible_tools"),
            "visible_tool_names": model_usage.get("visible_tool_names", []),
            "latency_seconds": round(wall_seconds, 4),
            "main_model_alias": model_alias,
            "main_model_name": model_name,
            "model_names": model_usage.get("model_names", []),
            "selector_model_alias": selector_alias if selector_usage.get("call_count") else None,
            "selector_model_name": (
                selector_model_name if selector_usage.get("call_count") else None
            ),
            "model_input_tokens": input_tokens,
            "model_output_tokens": output_tokens,
            "model_total_tokens": model_usage.get("total_tokens"),
            "selector_input_tokens": selector_input,
            "selector_output_tokens": selector_output,
            "selector_total_tokens": selector_usage.get("total_tokens"),
            "total_tokens": total_tokens,
            "token_usage_source": model_usage.get("usage_sources"),
            "model_token_coverage": model_usage.get("token_coverage"),
            "selector_token_coverage": selector_usage.get("token_coverage"),
            "estimated_cost_usd": estimated_cost,
            "duplicate_draft_count": duplicate_drafts,
            "duplicate_draft_rate": 1.0 if duplicate_drafts else 0.0,
            "pending_hitl_tools": pending_names,
            "hitl_requested_tools": requested_names,
            "hitl_completion_rate": hitl_usage.get("completion_rate"),
            "hitl_approved_count": hitl_usage.get("approved_count"),
            "hitl_completed_count": hitl_usage.get("completed_count"),
            "draft_plan_count": plan_count,
            "tool_calls": trace,
            "final_response": _UUID_TEXT.sub("<synthetic-id>", final_response),
        }

    @staticmethod
    def _usage_for_requests(request_ids: list[str]) -> dict[str, Any]:
        rows = list(
            LLMCallAudit.objects.filter(
                request_id__in=request_ids, component="time_steward"
            ).values(
                "status",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "duration_ms",
                "usage_source",
                "prompt_breakdown",
                "model_name",
            )
        )
        completed = [row for row in rows if row["status"] == "completed"]
        visible_counts = [
            int(row["prompt_breakdown"]["visible_tool_count"])
            for row in completed
            if isinstance(row["prompt_breakdown"], dict)
            and isinstance(row["prompt_breakdown"].get("visible_tool_count"), int)
        ]
        visible_names = sorted(
            {
                str(name)
                for row in completed
                if isinstance(row["prompt_breakdown"], dict)
                for name in row["prompt_breakdown"].get("visible_tool_names", [])
                if isinstance(name, str)
            }
        )

        def sum_known(key: str) -> int | None:
            values: list[int] = []
            for row in completed:
                value = row.get(key)
                if isinstance(value, bool):
                    return None
                if isinstance(value, int):
                    values.append(value)
                elif value is not None:
                    return None
            return sum(values) if rows and len(values) == len(rows) else None

        token_complete_count = sum(
            row["input_tokens"] is not None
            and row["output_tokens"] is not None
            and row["total_tokens"] is not None
            for row in completed
        )

        return {
            "model_call_count": len(rows),
            "completed_model_call_count": len(completed),
            "input_tokens": sum_known("input_tokens"),
            "output_tokens": sum_known("output_tokens"),
            "total_tokens": sum_known("total_tokens"),
            "model_duration_ms": sum(int(row["duration_ms"]) for row in completed),
            "usage_sources": sorted({str(row["usage_source"]) for row in completed}),
            "token_coverage": (round(token_complete_count / len(rows), 4) if rows else 1.0),
            "model_names": sorted({str(row["model_name"]) for row in rows}),
            "mean_visible_tools": (
                round(sum(visible_counts) / len(visible_counts), 2) if visible_counts else None
            ),
            "visible_tool_names": visible_names,
        }

    @staticmethod
    def _tool_trace(messages: Any) -> list[dict[str, Any]]:
        from langchain_core.messages import AIMessage, ToolMessage

        if not isinstance(messages, (list, tuple)):
            return []
        status_by_id = {
            str(message.tool_call_id): message
            for message in messages
            if isinstance(message, ToolMessage)
        }
        trace: list[dict[str, Any]] = []
        seen: set[str] = set()
        for message in messages:
            if not isinstance(message, AIMessage):
                continue
            for call in message.tool_calls:
                call_id = str(call.get("id", ""))
                if call_id and call_id in seen:
                    continue
                if call_id:
                    seen.add(call_id)
                tool_message = status_by_id.get(call_id)
                payload: dict[str, Any] = {}
                if tool_message is not None and tool_message.status == "error":
                    try:
                        raw = json.loads(str(tool_message.content))
                        payload = raw if isinstance(raw, dict) else {}
                    except json.JSONDecodeError:
                        payload = {}
                args = call.get("args", {})
                trace.append(
                    {
                        "name": str(call.get("name", "")),
                        "status": tool_message.status if tool_message is not None else "pending",
                        "error_code": payload.get("code"),
                        "safe_arguments": _safe_arguments(args),
                    }
                )
        return trace

    @staticmethod
    def _final_response(messages: Any) -> str:
        from langchain_core.messages import AIMessage

        if not isinstance(messages, (list, tuple)):
            return ""
        return next(
            (
                str(message.content)
                for message in reversed(messages)
                if isinstance(message, AIMessage)
            ),
            "",
        )

    @staticmethod
    def _interrupt_tool_names(interrupts: Any) -> list[str]:
        if not isinstance(interrupts, (list, tuple)):
            return []
        names: set[str] = set()
        for interrupt in interrupts:
            value = getattr(interrupt, "value", None)
            requests = value.get("action_requests", []) if isinstance(value, dict) else []
            if isinstance(requests, list):
                names.update(
                    str(item["name"])
                    for item in requests
                    if isinstance(item, dict) and isinstance(item.get("name"), str)
                )
        return sorted(names)

    @staticmethod
    def _hitl_metrics(proposal_ids: list[str]) -> dict[str, int | float | None]:
        if not proposal_ids:
            return {"approved_count": 0, "completed_count": 0, "completion_rate": None}
        proposals = list(ActionProposal.objects.filter(pk__in=proposal_ids))
        approved = [item for item in proposals if item.decision_type == "approve"]
        completed = [item for item in approved if item.status == "executed"]
        return {
            "approved_count": len(approved),
            "completed_count": len(completed),
            "completion_rate": round(len(completed) / len(approved), 4) if approved else None,
        }

    @staticmethod
    def _plan_has_exact_local_time(
        *,
        user: User,
        task_by_title: dict[str, Any],
        task_title: str,
        local_time_value: str,
        timezone_name: str,
    ) -> bool:
        task_ids = {str(task.pk) for title, task in task_by_title.items() if title == task_title}
        timezone = ZoneInfo(timezone_name)
        for plan in SchedulePlan.objects.filter(user=user, status=SchedulePlanStatus.DRAFT):
            for item in plan.items:
                if not isinstance(item, dict) or str(item.get("task_id", "")) not in task_ids:
                    continue
                if item.get("state") != "placed" or not isinstance(item.get("start_at"), str):
                    continue
                try:
                    actual = datetime.fromisoformat(item["start_at"].replace("Z", "+00:00"))
                except ValueError:
                    continue
                if actual.astimezone(timezone).strftime("%H:%M") == local_time_value:
                    return True
        return False

    @staticmethod
    def _looks_like_clarification(response: str) -> bool:
        lowered = response.casefold()
        return any(marker.casefold() in lowered for marker in _CLARIFICATION_MARKERS)

    @staticmethod
    def _empty_selector_metrics() -> dict[str, Any]:
        return {
            "call_count": 0,
            "completed_call_count": 0,
            "failed_call_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "token_coverage": None,
            "latency_ms_total": 0,
            "latency_ms_mean": None,
            "latency_ms_p50": None,
            "latency_ms_p95": None,
        }

    @staticmethod
    def _estimated_cost(
        *,
        input_tokens: object,
        output_tokens: object,
        selector_input_tokens: object,
        selector_output_tokens: object,
        prices: dict[str, float | None],
    ) -> float | None:
        if not isinstance(input_tokens, int | float):
            return None
        if not isinstance(output_tokens, int | float):
            return None
        if not isinstance(selector_input_tokens, int | float):
            return None
        if not isinstance(selector_output_tokens, int | float):
            return None
        model_input = prices.get("model_input")
        model_output = prices.get("model_output")
        selector_input = prices.get("selector_input")
        selector_output = prices.get("selector_output")
        if (
            model_input is None
            or model_output is None
            or selector_input is None
            or selector_output is None
        ):
            return None
        cost = (
            float(input_tokens) * model_input
            + float(output_tokens) * model_output
            + float(selector_input_tokens) * selector_input
            + float(selector_output_tokens) * selector_output
        ) / 1_000_000
        return round(cost, 8)

    @staticmethod
    def _prices(
        options: dict[str, Any], model_alias: str, selector_alias: str
    ) -> dict[str, float | None]:
        model_input = options.get("model_input_usd_per_million")
        model_output = options.get("model_output_usd_per_million")
        selector_input = options.get("selector_input_usd_per_million")
        selector_output = options.get("selector_output_usd_per_million")
        if selector_alias == model_alias:
            selector_input = model_input if selector_input is None else selector_input
            selector_output = model_output if selector_output is None else selector_output
        return {
            "model_input": model_input,
            "model_output": model_output,
            "selector_input": selector_input,
            "selector_output": selector_output,
        }

    @staticmethod
    def _summaries(
        rows: list[dict[str, Any]],
        variants: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for variant in variants:
            selected = [row for row in rows if row.get("variant") == variant["id"]]
            if not selected:
                continue
            trace_rows = [
                row
                for row in selected
                if row.get("trajectory_complete") is True
                or ("trajectory_complete" not in row and isinstance(row.get("tool_calls"), list))
            ]
            latencies = [
                float(row["latency_seconds"]) for row in selected if "latency_seconds" in row
            ]
            token_values = [
                int(row["total_tokens"])
                for row in selected
                if isinstance(row.get("total_tokens"), int)
            ]
            model_input_values = [
                int(row["model_input_tokens"])
                for row in selected
                if isinstance(row.get("model_input_tokens"), int)
            ]
            model_output_values = [
                int(row["model_output_tokens"])
                for row in selected
                if isinstance(row.get("model_output_tokens"), int)
            ]
            selector_input_values = [
                int(row["selector_input_tokens"])
                for row in selected
                if isinstance(row.get("selector_input_tokens"), int)
            ]
            selector_output_values = [
                int(row["selector_output_tokens"])
                for row in selected
                if isinstance(row.get("selector_output_tokens"), int)
            ]
            costs = [
                float(row["estimated_cost_usd"])
                for row in selected
                if isinstance(row.get("estimated_cost_usd"), int | float)
            ]
            expected_hitl = [row for row in selected if row.get("success_mode") == "hitl_roundtrip"]
            main_model_calls = sum(int(row.get("model_call_count") or 0) for row in selected)
            selector_calls = sum(int(row.get("selector_call_count") or 0) for row in selected)
            main_model_token_complete_calls = sum(
                round(
                    int(row.get("model_call_count") or 0)
                    * float(row.get("model_token_coverage") or 0)
                )
                for row in selected
            )
            selector_token_complete_calls = sum(
                round(
                    int(row.get("selector_call_count") or 0)
                    * float(row.get("selector_token_coverage") or 0)
                )
                for row in selected
            )
            model_token_covered_trials = sum(
                isinstance(row.get("model_total_tokens"), int) for row in selected
            )
            total_token_covered_trials = len(token_values)
            cost_covered_trials = len(costs)
            hitl_requested_runs = sum(
                bool(row.get("hitl_requested_tools")) for row in expected_hitl
            )
            hitl_completed_runs = sum(
                int(row.get("hitl_completed_count") or 0) > 0 for row in expected_hitl
            )
            required_recall_rows = [
                row for row in selected if isinstance(row.get("required_tool_recall"), int | float)
            ]
            required_recall_expected_rows = [row for row in selected if row.get("required_tools")]
            selected_recall_rows = [
                row for row in selected if isinstance(row.get("selected_tool_recall"), int | float)
            ]
            selected_precision_rows = [
                row
                for row in selected
                if isinstance(row.get("selected_tool_precision"), int | float)
            ]
            allowed_precision_rows = [
                row
                for row in trace_rows
                if isinstance(row.get("allowed_tool_precision"), int | float)
            ]
            wrong_tool_rows = [
                row for row in trace_rows if isinstance(row.get("wrong_tool_rate"), int | float)
            ]
            clarification_rows = [
                row for row in selected if isinstance(row.get("clarification_requested"), bool)
            ]
            tool_call_rows = [
                row for row in trace_rows if isinstance(row.get("tool_call_count"), int)
            ]
            duplicate_draft_rows = [
                row for row in trace_rows if isinstance(row.get("duplicate_draft_count"), int)
            ]
            hitl_completion_rows = [
                row
                for row in expected_hitl
                if isinstance(row.get("hitl_completion_rate"), int | float)
            ]
            hitl_pending_rows = [
                row for row in selected if isinstance(row.get("pending_hitl_tools"), list)
            ]
            output[variant["id"]] = {
                "strategy": variant["settings"].strategy,
                "parameters": {
                    "lexical_top_k": variant["settings"].lexical_top_k,
                    "candidate_top_k": variant["settings"].candidate_top_k,
                    "selector_max_tools": variant["settings"].selector_max_tools,
                },
                "run_count": len(selected),
                "failed_run_count": sum(bool(row.get("error_type")) for row in selected),
                "task_success_rate": round(
                    sum(bool(row.get("task_success")) for row in selected) / len(selected), 4
                ),
                "trajectory_covered_trial_count": len(trace_rows),
                "trajectory_trial_coverage": round(len(trace_rows) / len(selected), 4),
                "required_tool_recall": _mean_optional(
                    [row.get("required_tool_recall") for row in required_recall_rows]
                ),
                "required_tool_recall_covered_trial_count": len(required_recall_rows),
                "required_tool_recall_expected_trial_count": len(required_recall_expected_rows),
                "required_tool_recall_trial_coverage": round(
                    len(required_recall_rows) / len(required_recall_expected_rows), 4
                )
                if required_recall_expected_rows
                else None,
                "selected_tool_recall": _mean_optional(
                    [row.get("selected_tool_recall") for row in selected_recall_rows]
                ),
                "selected_tool_recall_covered_trial_count": len(selected_recall_rows),
                "selected_tool_recall_trial_coverage": round(
                    len(selected_recall_rows) / len(required_recall_expected_rows), 4
                )
                if required_recall_expected_rows
                else None,
                "selected_tool_precision": _mean_optional(
                    [row.get("selected_tool_precision") for row in selected_precision_rows]
                ),
                "selected_tool_precision_covered_trial_count": len(selected_precision_rows),
                "selected_tool_precision_trial_coverage": round(
                    len(selected_precision_rows) / len(selected), 4
                ),
                "allowed_tool_precision": _mean_optional(
                    [row.get("allowed_tool_precision") for row in allowed_precision_rows]
                ),
                "allowed_tool_precision_covered_trial_count": len(allowed_precision_rows),
                "allowed_tool_precision_trial_coverage": round(
                    len(allowed_precision_rows) / len(selected), 4
                ),
                "mean_hard_allowed_tool_count": _mean_optional(
                    [row.get("hard_allowed_tool_count_mean") for row in selected]
                ),
                "hard_allowed_tool_names_union": sorted(
                    {
                        name
                        for row in selected
                        for name in row.get("hard_allowed_tool_names_union", [])
                    }
                ),
                "wrong_tool_rate": _mean_optional(
                    [row.get("wrong_tool_rate") for row in wrong_tool_rows]
                ),
                "wrong_tool_metric_covered_trial_count": len(wrong_tool_rows),
                "wrong_tool_metric_trial_coverage": round(len(wrong_tool_rows) / len(selected), 4),
                "forbidden_tool_call_rate": (
                    round(
                        sum(bool(row.get("forbidden_tool_call_count")) for row in trace_rows)
                        / len(trace_rows),
                        4,
                    )
                    if trace_rows
                    else None
                ),
                "tool_surface_mismatch_rate": (
                    round(
                        sum(bool(row.get("tool_surface_mismatch_count")) for row in trace_rows)
                        / len(trace_rows),
                        4,
                    )
                    if trace_rows
                    else None
                ),
                "unauthorized_tool_call_count": sum(
                    int(row.get("unauthorized_tool_call_count", 0)) for row in trace_rows
                ),
                "clarification_rate": _mean_optional(
                    [float(bool(row.get("clarification_requested"))) for row in clarification_rows]
                ),
                "clarification_covered_trial_count": len(clarification_rows),
                "clarification_trial_coverage": round(len(clarification_rows) / len(selected), 4),
                "mean_agent_steps": round(
                    sum(int(row.get("agent_step_count", 0)) for row in selected) / len(selected), 4
                ),
                "mean_tool_calls": _mean_optional(
                    [row.get("tool_call_count") for row in tool_call_rows]
                ),
                "tool_call_count_covered_trial_count": len(tool_call_rows),
                "tool_call_count_trial_coverage": round(len(tool_call_rows) / len(selected), 4),
                "mean_selector_calls": round(
                    sum(int(row.get("selector_call_count", 0)) for row in selected) / len(selected),
                    4,
                ),
                "mean_selector_latency_ms": _mean_optional(
                    [row.get("selector_latency_ms_mean") for row in selected]
                ),
                "selector_latency_p50_ms": _percentile(
                    [
                        float(row["selector_latency_ms_p50"])
                        for row in selected
                        if isinstance(row.get("selector_latency_ms_p50"), int | float)
                    ],
                    0.50,
                ),
                "selector_latency_p95_ms": _percentile(
                    [
                        float(row["selector_latency_ms_p95"])
                        for row in selected
                        if isinstance(row.get("selector_latency_ms_p95"), int | float)
                    ],
                    0.95,
                ),
                "mean_visible_tools": round(
                    sum(float(row.get("mean_visible_tools") or 0) for row in selected)
                    / len(selected),
                    4,
                ),
                "latency_p50_seconds": _percentile(latencies, 0.50),
                "latency_p95_seconds": _percentile(latencies, 0.95),
                "mean_main_input_tokens_per_task": _mean_optional(
                    [row.get("model_input_tokens") for row in selected]
                ),
                "main_input_token_covered_trial_count": len(model_input_values),
                "main_input_token_trial_coverage": round(
                    len(model_input_values) / len(selected), 4
                ),
                "mean_main_output_tokens_per_task": _mean_optional(
                    [row.get("model_output_tokens") for row in selected]
                ),
                "main_output_token_covered_trial_count": len(model_output_values),
                "main_output_token_trial_coverage": round(
                    len(model_output_values) / len(selected), 4
                ),
                "mean_main_model_tokens_per_task": _mean_optional(
                    [row.get("model_total_tokens") for row in selected]
                ),
                "main_model_token_covered_trial_count": model_token_covered_trials,
                "main_model_token_trial_coverage": round(
                    model_token_covered_trials / len(selected), 4
                ),
                "main_model_call_count": main_model_calls,
                "main_model_token_complete_call_count": main_model_token_complete_calls,
                "main_model_token_call_coverage": (
                    round(main_model_token_complete_calls / main_model_calls, 4)
                    if main_model_calls
                    else None
                ),
                "mean_selector_tokens_per_task": _mean_optional(
                    [row.get("selector_total_tokens") for row in selected]
                ),
                "mean_selector_input_tokens_per_task": _mean_optional(
                    [row.get("selector_input_tokens") for row in selected]
                ),
                "selector_input_token_covered_trial_count": len(selector_input_values),
                "selector_input_token_trial_coverage": round(
                    len(selector_input_values) / len(selected), 4
                ),
                "mean_selector_output_tokens_per_task": _mean_optional(
                    [row.get("selector_output_tokens") for row in selected]
                ),
                "selector_output_token_covered_trial_count": len(selector_output_values),
                "selector_output_token_trial_coverage": round(
                    len(selector_output_values) / len(selected), 4
                ),
                "selector_call_count": selector_calls,
                "selector_token_complete_call_count": selector_token_complete_calls,
                "selector_token_call_coverage": (
                    round(selector_token_complete_calls / selector_calls, 4)
                    if selector_calls
                    else None
                ),
                "total_token_covered_trial_count": total_token_covered_trials,
                "total_token_trial_coverage": round(total_token_covered_trials / len(selected), 4),
                "mean_total_tokens_per_task": round(sum(token_values) / len(token_values), 2)
                if token_values
                else None,
                "estimated_cost_covered_trial_count": cost_covered_trials,
                "estimated_cost_trial_coverage": round(cost_covered_trials / len(selected), 4),
                "mean_estimated_cost_usd_per_task": round(sum(costs) / len(costs), 8)
                if costs
                else None,
                "duplicate_draft_rate": _mean_optional(
                    [float(bool(row.get("duplicate_draft_count"))) for row in duplicate_draft_rows]
                ),
                "duplicate_draft_covered_trial_count": len(duplicate_draft_rows),
                "duplicate_draft_trial_coverage": round(
                    len(duplicate_draft_rows) / len(selected), 4
                ),
                "hitl_case_count": len(expected_hitl),
                "hitl_requested_run_count": hitl_requested_runs,
                "hitl_approved_action_count": sum(
                    int(row.get("hitl_approved_count") or 0) for row in expected_hitl
                ),
                "hitl_completed_run_count": hitl_completed_runs,
                "hitl_roundtrip_success_rate": (
                    round(
                        sum(bool(row.get("task_success")) for row in expected_hitl)
                        / len(expected_hitl),
                        4,
                    )
                    if expected_hitl
                    else None
                ),
                "hitl_completion_rate": _mean_optional(
                    [row.get("hitl_completion_rate") for row in hitl_completion_rows]
                ),
                "hitl_completion_rate_covered_run_count": len(hitl_completion_rows),
                "hitl_completion_rate_trial_coverage": (
                    round(len(hitl_completion_rows) / len(expected_hitl), 4)
                    if expected_hitl
                    else None
                ),
                "hitl_pending_rate": _mean_optional(
                    [float(bool(row.get("pending_hitl_tools"))) for row in hitl_pending_rows]
                ),
                "hitl_pending_covered_trial_count": len(hitl_pending_rows),
                "hitl_pending_trial_coverage": round(len(hitl_pending_rows) / len(selected), 4),
            }
        return output

    @staticmethod
    def _case_hash(case: dict[str, Any]) -> str:
        serialized = json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise CommandError("Evaluation anchor must include a timezone")
        return parsed.astimezone(UTC)

    @staticmethod
    def _write_json(path: Path, document: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)


def _safe_arguments(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    def sanitize(item: Any, key: str | None = None) -> Any:
        if key in _PRIVATE_ARGUMENT_KEYS:
            return "<synthetic-id>"
        if key is not None and key.casefold() in _SENSITIVE_ARGUMENT_KEYS:
            return "<redacted>"
        if isinstance(item, dict):
            return {
                str(child_key): sanitize(child_value, str(child_key))
                for child_key, child_value in item.items()
            }
        if isinstance(item, list | tuple):
            return [sanitize(child) for child in item]
        if isinstance(item, str):
            return _UUID_TEXT.sub("<synthetic-id>", item)
        if isinstance(item, int | float | bool) or item is None:
            return item
        return "<omitted>"

    return {str(key): sanitize(item, str(key)) for key, item in value.items()}


def _percentile(values: Sequence[int | float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * quantile) - 1))
    return round(ordered[index], 4)


def _mean_optional(values: list[Any]) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, int | float)]
    return round(sum(numeric) / len(numeric), 4) if numeric else None
