from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from langchain.agents.middleware import ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool

from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.context import RuntimeContext
from apps.agents.management.commands.evaluate_tool_discovery import (
    Command as EvaluateToolDiscoveryCommand,
)
from apps.agents.middleware import (
    SELECTED_TOOL_SURFACE_METADATA_KEY,
    SelectedToolSurfaceMiddleware,
    ToolPolicyMiddleware,
    _FunctionCallingStructuredOutputAdapter,
    _hitl_when,
    _planning_lifecycle_phase,
    _policy_recovery_tool_names,
    resolve_tool_policy,
)
from apps.agents.tool_discovery import (
    ToolDiscoverySettings,
    rank_tools,
    select_discovery_candidates,
)
from apps.agents.tools import TIME_STEWARD_TOOLS, TOOL_SPECS
from apps.preferences.snapshots import PlanningPreferencesSnapshot
from common.clock import FixedClock


class _MainModel(BaseChatModel):
    responses: list[AIMessage]
    response_index: int = 0
    bound_tool_surfaces: list[list[str]] = []

    @property
    def _llm_type(self) -> str:
        return "tool-discovery-main-test"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        del tool_choice, kwargs
        self.bound_tool_surfaces.append([tool.name for tool in tools if isinstance(tool, BaseTool)])
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        response = self.responses[self.response_index]
        self.response_index += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


class _SelectorModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "tool-discovery-selector-test"

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:
        del schema, kwargs
        return RunnableLambda(lambda _messages: {"tools": ["list_calendar_sync_status"]})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        raise AssertionError("The fake selector should use with_structured_output")


def _context(user: User, message: str, *, read_only: bool = False) -> RuntimeContext:
    anchor = datetime(2026, 7, 17, 8, tzinfo=UTC)
    return RuntimeContext(
        user_id=str(user.pk),
        request_id=str(uuid4()),
        timezone="Asia/Shanghai",
        locale="zh-CN",
        current_datetime=anchor,
        trigger_type="user_message",
        input_message=message,
        read_only=read_only,
        actor=user,
        planning_preferences=PlanningPreferencesSnapshot(),
        clock=FixedClock(anchor),
    )


def test_lexical_retrieval_ranks_chinese_exact_time_edit() -> None:
    ranked = rank_tools(
        "把论文改到 21:00",
        tool_specs=TOOL_SPECS,
        candidate_names=frozenset(TOOL_SPECS),
        limit=6,
    )

    assert ranked[0] == "edit_schedule_plan"


def test_function_calling_adapter_preserves_builtin_selector_schema():
    seen: dict[str, Any] = {}

    class Target:
        def with_structured_output(self, schema: Any, **kwargs: Any) -> object:
            seen["schema"] = schema
            seen.update(kwargs)
            return object()

    schema = {"type": "object", "properties": {"tools": {"type": "array"}}}
    adapter = _FunctionCallingStructuredOutputAdapter(cast(BaseChatModel, Target()))

    adapter.with_structured_output(schema)

    assert seen["schema"] == schema
    assert seen["method"] == "function_calling"


def test_lexical_retrieval_never_searches_outside_hard_allowed_tools() -> None:
    hard_allowed = frozenset({"list_tasks"})
    result = select_discovery_candidates(
        "创建新任务并安排计划",
        tool_specs=TOOL_SPECS,
        hard_allowed_names=hard_allowed,
        lifecycle_visible_names=hard_allowed,
        settings=ToolDiscoverySettings(strategy="lexical_retrieval", lexical_top_k=4),
        fallback_names=hard_allowed,
    )

    assert result.selected_tools == hard_allowed
    assert "create_task" not in result.selected_tools


def test_zero_match_lexical_retrieval_falls_back_to_regex_candidates() -> None:
    hard_allowed = frozenset({"list_tasks", "list_events", "get_task"})
    regex_candidates = frozenset({"list_tasks"})
    result = select_discovery_candidates(
        "嗯",
        tool_specs=TOOL_SPECS,
        hard_allowed_names=hard_allowed,
        lifecycle_visible_names=hard_allowed,
        settings=ToolDiscoverySettings(strategy="lexical_retrieval", lexical_top_k=4),
        fallback_names=regex_candidates,
    )

    assert result.selected_tools == regex_candidates
    assert result.fallback_reason == "lexical_no_match"


@pytest.mark.django_db(transaction=True)
def test_surface_capture_excludes_eager_write_tool_when_request_is_read_only() -> None:
    user = User.objects.create_user(username="tool-discovery-eager-safety")
    prompt = "\u540c\u6b65\u72b6\u6001"
    runtime_context = _context(user, prompt)
    model_request = cast(
        ModelRequest[RuntimeContext],
        SimpleNamespace(
            runtime=SimpleNamespace(context=runtime_context),
            messages=[HumanMessage(content=prompt)],
            tools=[TOOL_SPECS["list_calendar_sync_status"].tool],
        ),
    )
    middleware = SelectedToolSurfaceMiddleware(
        discovery_settings=ToolDiscoverySettings(
            strategy="llm_selector",
            always_include=("create_task",),
        )
    )

    result = middleware.wrap_model_call(
        model_request,
        lambda request: ModelResponse(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "list_calendar_sync_status",
                            "args": {},
                            "id": "sync-status",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        ),
    )

    assert isinstance(result, ModelResponse)
    assert result.result[0].response_metadata[SELECTED_TOOL_SURFACE_METADATA_KEY] == [
        "list_calendar_sync_status"
    ]


@pytest.mark.django_db(transaction=True)
def test_real_selector_surface_is_enforced_for_tool_calls() -> None:
    user = User.objects.create_user(username="tool-discovery-selector-surface")
    prompt = "\u540c\u6b65\u72b6\u6001"
    model = _MainModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_task",
                        "args": {"task_id": str(uuid4())},
                        "id": "unselected-read",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="\u5df2\u5728\u53ef\u7528\u8303\u56f4\u5185\u5904\u7406\u3002"),
        ]
    )
    agent = build_time_steward_agent(
        model=model,
        selector_model=_SelectorModel(),
        discovery_settings=ToolDiscoverySettings(
            strategy="llm_selector",
            selector_max_tools=4,
        ),
    )

    result = agent.invoke(
        {"messages": [HumanMessage(content=prompt)]},
        context=_context(user, prompt),
    )

    denied = next(
        message
        for message in result["messages"]
        if isinstance(message, ToolMessage) and message.name == "get_task"
    )
    assert json.loads(str(denied.content))["code"] == "tool_surface_mismatch"
    assert model.bound_tool_surfaces[0] == ["list_calendar_sync_status"]


def test_llm_discovery_requires_an_explicit_selector_model() -> None:
    with pytest.raises(ValueError, match="explicitly configured selector model"):
        build_time_steward_agent(
            model=_MainModel(responses=[]),
            discovery_settings=ToolDiscoverySettings(strategy="llm_selector"),
        )


@pytest.mark.django_db(transaction=True)
def test_dynamic_surface_uses_only_current_turn_for_plan_lifecycle() -> None:
    user = User.objects.create_user(username="tool-discovery-lifecycle")
    prompt = "schedule tasks for next week"
    settings = ToolDiscoverySettings(strategy="lexical_retrieval", lexical_top_k=8)
    messages = [
        HumanMessage(content="schedule tasks for next week"),
        ToolMessage(
            content=json.dumps({"plan_id": str(uuid4()), "version": 1, "items": []}),
            name="propose_schedule_plan",
            tool_call_id="proposal-call",
            status="success",
        ),
        HumanMessage(content=prompt),
    ]

    phase = _planning_lifecycle_phase(messages)
    decision = resolve_tool_policy(
        _context(user, prompt),
        planning_lifecycle_phase=phase,
        discovery_settings=settings,
    )

    assert phase == "no_plan"
    assert "propose_schedule_plan" in decision.visible_tools


@pytest.mark.django_db(transaction=True)
def test_current_turn_draft_hides_duplicate_proposal() -> None:
    user = User.objects.create_user(username="tool-discovery-current-lifecycle")
    prompt = "schedule tasks for next week"
    settings = ToolDiscoverySettings(strategy="lexical_retrieval", lexical_top_k=8)
    messages = [
        HumanMessage(content=prompt),
        ToolMessage(
            content=json.dumps({"plan_id": str(uuid4()), "version": 1, "items": []}),
            name="propose_schedule_plan",
            tool_call_id="current-proposal-call",
            status="success",
        ),
    ]

    phase = _planning_lifecycle_phase(messages)
    decision = resolve_tool_policy(
        _context(user, prompt),
        planning_lifecycle_phase=phase,
        discovery_settings=settings,
    )

    assert phase == "draft_created"
    assert "propose_schedule_plan" not in decision.visible_tools


@pytest.mark.django_db(transaction=True)
def test_selector_surface_mismatch_is_denied_before_tool_handler() -> None:
    user = User.objects.create_user(username="tool-discovery-selected-surface")
    prompt = "\u8bf7\u521b\u5efa\u4efb\u52a1\uff1a\u5468\u62a5"
    messages = [
        HumanMessage(content=prompt),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "create_task",
                    "args": {"title": "not selected"},
                    "id": "unselected-write",
                    "type": "tool_call",
                }
            ],
            response_metadata={SELECTED_TOOL_SURFACE_METADATA_KEY: ["list_tasks"]},
        ),
    ]
    request = cast(
        ToolCallRequest,
        SimpleNamespace(
            runtime=SimpleNamespace(context=_context(user, prompt)),
            state={"messages": messages},
            tool_call={
                "name": "create_task",
                "args": {"title": "not selected"},
                "id": "unselected-write",
                "type": "tool_call",
            },
        ),
    )
    called: list[str] = []

    def handler(_request: ToolCallRequest) -> str:
        called.append("create_task")
        return "unexpected"

    result = ToolPolicyMiddleware(
        discovery_settings=ToolDiscoverySettings(strategy="llm_selector")
    ).wrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert json.loads(str(result.content))["code"] == "tool_surface_mismatch"
    assert called == []


@pytest.mark.django_db(transaction=True)
def test_policy_recovery_exposes_only_immediately_mismatched_allowed_tool() -> None:
    user = User.objects.create_user(username="tool-discovery-narrow-recovery")
    prompt = "帮我安排明天的论文和周报"
    context = _context(user, prompt)
    settings = ToolDiscoverySettings(strategy="lexical_retrieval", lexical_top_k=4)
    decision = resolve_tool_policy(context, discovery_settings=settings)
    missing_candidates = decision.hard_allowed_tools - decision.visible_tools
    assert missing_candidates
    denied_name = sorted(missing_candidates)[0]
    denied_id = "surface-mismatch-recovery"
    messages = [
        HumanMessage(content=prompt),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": denied_name,
                    "args": {},
                    "id": denied_id,
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content=json.dumps({"code": "tool_surface_mismatch", "tool_name": denied_name}),
            name=denied_name,
            tool_call_id=denied_id,
            status="error",
        ),
    ]

    class OverridableRequest:
        runtime = SimpleNamespace(context=context)
        state = {"messages": messages}
        tools = list(TIME_STEWARD_TOOLS)

        def override(self, **updates: Any) -> SimpleNamespace:
            return SimpleNamespace(
                runtime=self.runtime,
                state=self.state,
                messages=messages,
                tools=updates["tools"],
            )

    recovered = ToolPolicyMiddleware(discovery_settings=settings)._request(
        cast(Any, OverridableRequest())
    )
    recovered_names = {tool.name for tool in recovered.tools}

    assert recovered_names == decision.visible_tools.union({denied_name})
    assert len(recovered_names) < len(decision.hard_allowed_tools)
    assert (
        _policy_recovery_tool_names(messages + [AIMessage(content="completed")], decision)
        == frozenset()
    )


@pytest.mark.django_db(transaction=True)
def test_recovered_high_risk_tool_still_triggers_hitl_when_selected() -> None:
    user = User.objects.create_user(username="tool-discovery-hitl-recovery")
    prompt = "就按这个计划执行"
    context = _context(user, prompt)
    settings = ToolDiscoverySettings(strategy="lexical_retrieval", lexical_top_k=1)
    decision = resolve_tool_policy(
        context,
        input_message=prompt,
        discovery_settings=settings,
    )
    assert "apply_schedule_plan" in decision.hard_allowed_tools
    assert "apply_schedule_plan" not in decision.visible_tools

    messages = [
        HumanMessage(content=prompt),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "apply_schedule_plan",
                    "args": {"plan_id": str(uuid4())},
                    "id": "initial-hidden-apply",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content=json.dumps(
                {"code": "tool_surface_mismatch", "tool_name": "apply_schedule_plan"}
            ),
            name="apply_schedule_plan",
            tool_call_id="initial-hidden-apply",
            status="error",
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "apply_schedule_plan",
                    "args": {"plan_id": str(uuid4())},
                    "id": "recovered-apply",
                    "type": "tool_call",
                }
            ],
            response_metadata={SELECTED_TOOL_SURFACE_METADATA_KEY: ["apply_schedule_plan"]},
        ),
    ]
    request = cast(
        ToolCallRequest,
        SimpleNamespace(
            runtime=SimpleNamespace(context=context),
            state={"messages": messages},
            tool_call={"name": "apply_schedule_plan", "args": {}, "id": "recovered-apply"},
        ),
    )

    assert _hitl_when("apply_schedule_plan", discovery_settings=settings)(request) is True


@pytest.mark.django_db(transaction=True)
def test_recovery_cannot_execute_high_risk_tool_missing_from_selected_surface() -> None:
    user = User.objects.create_user(username="tool-discovery-recovery-surface")
    prompt = "就按这个计划执行"
    context = _context(user, prompt)
    settings = ToolDiscoverySettings(strategy="lexical_retrieval", lexical_top_k=1)
    decision = resolve_tool_policy(
        context,
        input_message=prompt,
        discovery_settings=settings,
    )
    assert "apply_schedule_plan" in decision.hard_allowed_tools
    assert "apply_schedule_plan" not in decision.visible_tools

    messages = [
        HumanMessage(content=prompt),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "apply_schedule_plan",
                    "args": {"plan_id": str(uuid4())},
                    "id": "hidden-apply",
                    "type": "tool_call",
                }
            ],
            response_metadata={SELECTED_TOOL_SURFACE_METADATA_KEY: ["get_planning_context"]},
        ),
        ToolMessage(
            content=json.dumps(
                {"code": "tool_surface_mismatch", "tool_name": "apply_schedule_plan"}
            ),
            name="apply_schedule_plan",
            tool_call_id="hidden-apply",
            status="error",
        ),
    ]
    request = cast(
        ToolCallRequest,
        SimpleNamespace(
            runtime=SimpleNamespace(context=context),
            state={"messages": messages},
            tool_call={
                "name": "apply_schedule_plan",
                "args": {"plan_id": str(uuid4())},
                "id": "recovered-hidden-apply",
                "type": "tool_call",
            },
        ),
    )
    called: list[str] = []

    def handler(_request: ToolCallRequest) -> str:
        called.append("apply_schedule_plan")
        return "unexpected"

    result = ToolPolicyMiddleware(discovery_settings=settings).wrap_tool_call(
        request,
        handler,
    )

    assert isinstance(result, ToolMessage)
    assert json.loads(str(result.content))["code"] == "tool_surface_mismatch"
    assert called == []


@pytest.mark.django_db(transaction=True)
def test_selector_cannot_make_a_hard_denied_tool_authorized() -> None:
    user = User.objects.create_user(username="tool-discovery-hard-denial")
    prompt = "\u540c\u6b65\u72b6\u6001"
    messages = [
        HumanMessage(content=prompt),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "create_task",
                    "args": {"title": "forbidden"},
                    "id": "unauthorized-write",
                    "type": "tool_call",
                }
            ],
            response_metadata={SELECTED_TOOL_SURFACE_METADATA_KEY: ["create_task"]},
        ),
    ]
    request = cast(
        ToolCallRequest,
        SimpleNamespace(
            runtime=SimpleNamespace(context=_context(user, prompt)),
            state={"messages": messages},
            tool_call={
                "name": "create_task",
                "args": {"title": "forbidden"},
                "id": "unauthorized-write",
                "type": "tool_call",
            },
        ),
    )
    called: list[str] = []

    def handler(_request: ToolCallRequest) -> str:
        called.append("create_task")
        return "unexpected"

    result = ToolPolicyMiddleware(
        discovery_settings=ToolDiscoverySettings(strategy="llm_selector")
    ).wrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert json.loads(str(result.content))["code"] == "tool_not_authorized"
    assert called == []


def test_tool_registry_size_matches_manifest_and_every_registered_tool_is_discoverable() -> None:
    names = {tool.name for tool in TIME_STEWARD_TOOLS}

    assert len(names) == len(TOOL_SPECS) == 45
    assert names == set(TOOL_SPECS)
    assert all(spec.searchable for spec in TOOL_SPECS.values())


def test_estimated_cost_uses_resolved_model_and_selector_prices() -> None:
    prices = EvaluateToolDiscoveryCommand._prices(
        {
            "model_input_usd_per_million": 0.3,
            "model_output_usd_per_million": 1.2,
        },
        "deepseek",
        "deepseek",
    )

    assert (
        EvaluateToolDiscoveryCommand._estimated_cost(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            selector_input_tokens=500_000,
            selector_output_tokens=250_000,
            prices=prices,
        )
        == 1.95
    )


def test_estimated_cost_keeps_independent_selector_prices() -> None:
    prices = EvaluateToolDiscoveryCommand._prices(
        {
            "model_input_usd_per_million": 0.3,
            "model_output_usd_per_million": 1.2,
            "selector_input_usd_per_million": 0.1,
            "selector_output_usd_per_million": 0.5,
        },
        "deepseek",
        "other-selector",
    )

    assert prices == {
        "model_input": 0.3,
        "model_output": 1.2,
        "selector_input": 0.1,
        "selector_output": 0.5,
    }


def test_evaluator_summary_reports_usage_and_hitl_denominators() -> None:
    variant = {"id": "A_regex_pack", "settings": ToolDiscoverySettings(strategy="regex_pack")}
    rows = [
        {
            "variant": "A_regex_pack",
            "task_success": False,
            "success_mode": "hitl_roundtrip",
            "required_tools": ["remember_time_preference"],
            "trajectory_complete": True,
            "latency_seconds": 2.0,
            "model_call_count": 1,
            "model_total_tokens": 100,
            "model_input_tokens": 60,
            "model_output_tokens": 40,
            "model_token_coverage": 1.0,
            "tool_call_count": 0,
            "tool_calls": [],
            "required_tool_recall": 0.0,
            "selector_call_count": 0,
            "selector_token_coverage": 1.0,
            "hitl_requested_tools": [],
            "hitl_completion_rate": None,
            "hitl_completed_count": 0,
            "estimated_cost_usd": None,
            "total_tokens": None,
        },
        {
            "variant": "A_regex_pack",
            "task_success": False,
            "success_mode": "hitl_roundtrip",
            "required_tools": ["remember_time_preference"],
            "trajectory_complete": False,
            "error_type": "AssertionError",
            "latency_seconds": 1.0,
            "model_call_count": 0,
            "model_token_coverage": 1.0,
            "tool_call_count": None,
            "required_tool_recall": 0.0,
            "selector_call_count": 1,
            "selector_token_coverage": 1.0,
            "hitl_requested_tools": [],
            "hitl_completion_rate": None,
            "hitl_completed_count": 0,
            "estimated_cost_usd": None,
            "total_tokens": None,
        },
    ]

    summary = EvaluateToolDiscoveryCommand._summaries(rows, [variant])["A_regex_pack"]

    assert summary["failed_run_count"] == 1
    assert summary["trajectory_covered_trial_count"] == 1
    assert summary["trajectory_trial_coverage"] == 0.5
    assert summary["required_tool_recall"] == 0.0
    assert summary["required_tool_recall_covered_trial_count"] == 2
    assert summary["required_tool_recall_expected_trial_count"] == 2
    assert summary["required_tool_recall_trial_coverage"] == 1.0
    assert summary["tool_call_count_covered_trial_count"] == 1
    assert summary["tool_call_count_trial_coverage"] == 0.5
    assert summary["main_model_token_covered_trial_count"] == 1
    assert summary["main_model_token_trial_coverage"] == 0.5
    assert summary["mean_main_input_tokens_per_task"] == 60.0
    assert summary["main_input_token_covered_trial_count"] == 1
    assert summary["main_input_token_trial_coverage"] == 0.5
    assert summary["mean_main_output_tokens_per_task"] == 40.0
    assert summary["main_model_call_count"] == 1
    assert summary["main_model_token_complete_call_count"] == 1
    assert summary["main_model_token_call_coverage"] == 1.0
    assert summary["selector_call_count"] == 1
    assert summary["selector_token_complete_call_count"] == 1
    assert summary["selector_token_call_coverage"] == 1.0
    assert summary["total_token_covered_trial_count"] == 0
    assert summary["estimated_cost_covered_trial_count"] == 0
    assert summary["hitl_case_count"] == 2
    assert summary["hitl_requested_run_count"] == 0
    assert summary["hitl_completed_run_count"] == 0
    assert summary["hitl_roundtrip_success_rate"] == 0.0
