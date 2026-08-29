import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from langchain.agents.middleware import ToolCallRequest
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.store.memory import InMemoryStore

from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.context import RuntimeContext
from apps.agents.management.commands.evaluate_time_steward import Command as AgentEvalCommand
from apps.agents.middleware import (
    TemporalContextMiddleware,
    ToolAuditMiddleware,
    ToolPolicyMiddleware,
    _hitl_when,
    build_time_steward_middleware,
)
from apps.agents.tools import READ_ONLY_TOOLS, TIME_STEWARD_TOOLS, WRITE_TOOLS
from apps.conversations.models import AgentRunStatus, ToolCallAudit, ToolCallStatus
from apps.conversations.services import AgentRunService, ConversationService, StartRunCommand
from apps.events.services import CreateEventCommand, EventService
from apps.integrations.calendar.sync_services import CalendarSyncService
from apps.observability.models import LLMCallAudit
from apps.preferences.snapshots import PlanningPreferencesSnapshot
from apps.tasks.execution_services import RecordExecutionSignalCommand, TaskExecutionSignalService
from apps.tasks.models import Task
from apps.tasks.services import CreateTaskCommand, TaskService
from apps.time_memory.models import TimeDecisionFeedback
from common.clock import FixedClock


class ScriptedChatModel(BaseChatModel):
    responses: list[AIMessage]
    response_index: int = 0
    bound_tool_names: list[str] = []
    received_messages: list[BaseMessage] = []

    @property
    def _llm_type(self) -> str:
        return "scripted-time-steward-test"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        del tool_choice, kwargs
        self.bound_tool_names = [tool.name for tool in tools if isinstance(tool, BaseTool)]
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.received_messages = messages
        del stop, run_manager, kwargs
        response = self.responses[self.response_index]
        self.response_index += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


def context(
    user: User,
    *,
    read_only: bool = False,
    agent_run_id: str | None = None,
    clock: FixedClock | None = None,
    planning_preferences: PlanningPreferencesSnapshot | None = None,
) -> RuntimeContext:
    values: dict[str, Any] = {
        "user_id": str(user.pk),
        "request_id": str(uuid4()),
        "timezone": "Asia/Shanghai",
        "locale": "zh-CN",
        "current_datetime": datetime(2026, 7, 17, 8, tzinfo=UTC),
        "trigger_type": "user_message",
        "conversation_id": str(uuid4()),
        "agent_run_id": agent_run_id,
        "read_only": read_only,
        "actor": user,
    }
    if clock is not None:
        values["clock"] = clock
    if planning_preferences is not None:
        values["planning_preferences"] = planning_preferences
    return RuntimeContext(**values)


def test_temporal_context_hides_historical_clock_calls_and_labels_ai_messages() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="What time is it?"),
        AIMessage(
            content="It is 2026-07-17 16:00.",
            tool_calls=[
                {
                    "name": "get_current_datetime",
                    "args": {},
                    "id": "historic-clock-call",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content='{"observed_datetime_local":"2026-07-17T16:00:00+08:00"}',
            name="get_current_datetime",
            tool_call_id="historic-clock-call",
        ),
        HumanMessage(content="Then schedule it tomorrow."),
    ]

    model_messages = TemporalContextMiddleware._model_messages(messages)

    historical_ai = next(message for message in model_messages if isinstance(message, AIMessage))
    assert str(historical_ai.content).startswith("[Historical assistant response from run anchor")
    assert historical_ai.tool_calls == []
    assert all(
        not (isinstance(message, ToolMessage) and message.name == "get_current_datetime")
        for message in model_messages
    )
    assert model_messages[-1].content == "Then schedule it tomorrow."
    historical_human = next(
        message for message in model_messages if isinstance(message, HumanMessage)
    )
    assert str(historical_human.content).startswith("[Historical user request")
    assert "16:00" in str(historical_ai.content)

    # The checkpoint/history source is untouched.
    assert messages[1].content == "It is 2026-07-17 16:00."
    assert isinstance(messages[2], ToolMessage)


@pytest.mark.django_db(transaction=True)
def test_calendar_hitl_preferences_allow_safe_create_and_cancellation_only() -> None:
    user = User.objects.create_user(username="calendar-policy")
    preferences = PlanningPreferencesSnapshot(
        require_event_creation_approval=False,
        require_event_cancellation_approval=False,
    )
    runtime_context = context(user, planning_preferences=preferences)
    requires_review = _hitl_when("mutate_events")

    def request_for(operation: Mapping[str, object]) -> ToolCallRequest:
        return cast(
            ToolCallRequest,
            SimpleNamespace(
                runtime=SimpleNamespace(context=runtime_context),
                tool_call={"args": {"operations": [dict(operation)]}},
            ),
        )

    safe_create = {
        "action": "create",
        "title": "Focus time",
        "time": {
            "kind": "absolute",
            "start_at": "2026-07-18T10:00:00+08:00",
            "end_at": "2026-07-18T11:00:00+08:00",
        },
    }
    assert requires_review(request_for(safe_create)) is False

    event = EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Existing commitment",
            start_at=datetime(2026, 7, 18, 2, tzinfo=UTC),
            end_at=datetime(2026, 7, 18, 3, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )
    conflicting_create = {
        **safe_create,
        "time": {
            "kind": "absolute",
            "start_at": "2026-07-18T10:30:00+08:00",
            "end_at": "2026-07-18T11:30:00+08:00",
        },
    }
    assert requires_review(request_for(conflicting_create)) is True
    assert (
        requires_review(
            request_for({"action": "cancel", "event_id": str(event.pk), "expected_version": 1})
        )
        is False
    )

    protected_context = context(
        user,
        planning_preferences=PlanningPreferencesSnapshot(
            require_event_creation_approval=True,
            require_event_cancellation_approval=True,
        ),
    )
    protected_request = SimpleNamespace(
        runtime=SimpleNamespace(context=protected_context),
        tool_call={"args": {"operations": [safe_create]}},
    )
    assert _hitl_when("mutate_events")(protected_request) is True  # type: ignore[arg-type]


@pytest.mark.django_db(transaction=True)
def test_time_tool_returns_fixed_run_anchor_and_realtime_clock() -> None:
    user = User.objects.create_user(username="clock-reader")
    observed_time = datetime(2026, 7, 17, 8, 5, tzinfo=UTC)
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_current_datetime",
                        "args": {},
                        "id": "read-time-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="The time is confirmed."),
        ]
    )
    agent = build_time_steward_agent(model=model)

    result = agent.invoke(
        {"messages": [HumanMessage(content="What time is it?")]},
        context=context(user, read_only=True, clock=FixedClock(observed_time)),
    )

    tool_message = next(
        message for message in result["messages"] if isinstance(message, ToolMessage)
    )
    payload = json.loads(str(tool_message.content))
    assert payload["run_anchor_datetime_utc"] == "2026-07-17T08:00:00+00:00"
    assert payload["observed_datetime_utc"] == "2026-07-17T08:05:00+00:00"
    assert payload["observed_datetime_local"] == "2026-07-17T16:05:00+08:00"


@pytest.mark.django_db(transaction=True)
def test_agent_injects_runtime_preferences_and_nickname_without_preference_tool() -> None:
    user = User.objects.create_user(username="planning-reader", first_name="小林")
    model = ScriptedChatModel(responses=[AIMessage(content="I'll use your work hours.")])
    agent = build_time_steward_agent(model=model)
    preferences = PlanningPreferencesSnapshot(
        workday_start="08:30",
        workday_end="17:30",
        default_reminder_offsets=(30, 120),
    )

    result = agent.invoke(
        {"messages": [HumanMessage(content="Plan my afternoon.")]},
        context=RuntimeContext(
            user_id=str(user.pk),
            request_id=str(uuid4()),
            timezone="Asia/Shanghai",
            locale="zh-CN",
            current_datetime=datetime(2026, 7, 17, 8, tzinfo=UTC),
            trigger_type="user_message",
            conversation_id=str(uuid4()),
            actor=user,
            planning_preferences=preferences,
        ),
    )

    prompt = next(
        message for message in model.received_messages if isinstance(message, SystemMessage)
    )
    assert '工作开始="08:30"' in str(prompt.content)
    assert "默认提醒提前量（分钟）=[30, 120]" in str(prompt.content)
    assert "时间优先级规则" in str(prompt.content)
    assert '偏好称呼 JSON="小林"' in str(prompt.content)
    assert "get_user_preferences" not in model.bound_tool_names
    assert all(not isinstance(message, SystemMessage) for message in result["messages"])


@pytest.mark.django_db(transaction=True)
def test_create_agent_executes_read_tool_with_trusted_runtime_actor() -> None:
    user = User.objects.create_user(username="reader")
    event = EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Design review",
            start_at=datetime(2026, 7, 18, 1, tzinfo=UTC),
            end_at=datetime(2026, 7, 18, 2, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_event",
                        "args": {"event_id": str(event.pk)},
                        "id": "read-event-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="你的设计评审在明天上午。"),
        ]
    )
    agent = build_time_steward_agent(model=model)

    result = agent.invoke(
        {"messages": [HumanMessage(content="我的设计评审是什么时候？")]},
        context=context(user, read_only=True),
    )

    tool_message = next(
        message for message in result["messages"] if isinstance(message, ToolMessage)
    )
    assert "Design review" in str(tool_message.content)
    assert result["messages"][-1].content == "你的设计评审在明天上午。"
    assert set(model.bound_tool_names) == {tool.name for tool in READ_ONLY_TOOLS}


@pytest.mark.django_db(transaction=True)
def test_low_risk_write_is_audited_and_bound_to_current_user() -> None:
    user = User.objects.create_user(username="writer")
    conversation = ConversationService.create(user=user)
    run = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="request-1",
            message="创建任务",
        )
    )
    run = AgentRunService.mark_running(run)
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_task",
                        "args": {"title": "提交报告"},
                        "id": "create-task-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="任务已创建。"),
        ]
    )
    agent = build_time_steward_agent(model=model)

    result = agent.invoke(
        {"messages": [HumanMessage(content="创建提交报告任务")]},
        context=context(user, agent_run_id=str(run.pk)),
    )

    assert result["messages"][-1].content == "任务已创建。"
    assert Task.objects.get().user == user
    audit = ToolCallAudit.objects.get()
    assert audit.status == ToolCallStatus.COMPLETED
    assert audit.tool_name == "create_task"
    assert audit.risk_level == "low"
    assert list(run.events.values_list("event_type", flat=True)) == [
        "agent.started",
        "tool.started",
        "tool.completed",
    ]
    assert run.status == AgentRunStatus.RUNNING


@pytest.mark.django_db
def test_tool_failure_is_audited_and_emitted() -> None:
    user = User.objects.create_user(username="async-writer")
    conversation = ConversationService.create(user=user)
    run = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="request-async-failure",
            message="创建任务",
        )
    )
    run = AgentRunService.mark_running(run)
    request = cast(
        ToolCallRequest,
        SimpleNamespace(
            runtime=SimpleNamespace(context=context(user, agent_run_id=str(run.pk))),
            tool_call={
                "name": "create_task",
                "args": {"title": "失败任务"},
                "id": "create-task-failure",
                "type": "tool_call",
            },
        ),
    )

    def fail_create(_request: ToolCallRequest) -> None:
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        ToolAuditMiddleware().wrap_tool_call(request, fail_create)

    audit = ToolCallAudit.objects.get(tool_call_id="create-task-failure")
    assert audit.status == ToolCallStatus.FAILED
    assert list(run.events.values_list("event_type", flat=True)) == [
        "agent.started",
        "tool.started",
        "tool.failed",
    ]


def test_official_middleware_and_fixed_eval_policy_cover_phase_five() -> None:
    model = ScriptedChatModel(responses=[AIMessage(content="done")])
    middleware = build_time_steward_middleware(model)
    names = {type(item).__name__ for item in middleware}
    assert {
        "ToolPolicyMiddleware",
        "ToolAuditMiddleware",
        "ModelCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "ModelRetryMiddleware",
        "ToolRetryMiddleware",
        "ToolErrorMiddleware",
        "SummarizationMiddleware",
    }.issubset(names)
    assert any(isinstance(item, ToolPolicyMiddleware) for item in middleware)
    assert any(isinstance(item, TemporalContextMiddleware) for item in middleware)
    ablated_names = {
        type(item).__name__
        for item in build_time_steward_middleware(model, temporal_context_enabled=False)
    }
    assert "TemporalContextMiddleware" not in ablated_names
    assert "ToolPolicyMiddleware" in ablated_names

    fallback = ScriptedChatModel(responses=[AIMessage(content="fallback")])
    fallback_names = {
        type(item).__name__
        for item in build_time_steward_middleware(model, fallback_models=[fallback])
    }
    assert "ModelFallbackMiddleware" in fallback_names

    cases = json.loads(
        (Path(__file__).parent / "fixtures" / "time_steward_eval.json").read_text(encoding="utf-8")
    )
    registered = {tool.name for tool in TIME_STEWARD_TOOLS}
    write_names = {tool.name for tool in WRITE_TOOLS}
    assert len(cases) >= 4
    assert {"system-prompt-exfiltration", "credential-exfiltration"}.issubset(
        {case["id"] for case in cases}
    )
    for case in cases:
        assert set(case["required_tools"]).issubset(registered)
        assert set(case["required_tools"]).issubset(set(case["allowed_tools"]))
        assert set(case["allowed_tools"]).issubset(registered)
        assert set(case["forbidden_tools"]).isdisjoint(set(case["required_tools"]))
    assert write_names == {
        "mutate_events",
        "create_recurring_event",
        "create_task",
        "create_task_batch",
        "update_task",
        "change_task_state",
        "change_task_batch_state",
        "complete_task",
        "reschedule_task",
        "cancel_task",
        "create_reminder",
        "update_reminder",
        "set_reminder_target",
        "cancel_reminder",
        "apply_schedule_plan",
        "apply_local_replan",
        "record_task_duration_feedback",
        "act_on_temporal_insight",
        "validate_schedule_plan",
        "set_schedule_plan_item_lock",
        "abandon_schedule_plan",
    }


@pytest.mark.django_db(transaction=True)
def test_agent_reads_duration_recommendation_and_capacity_from_services() -> None:
    user = User.objects.create_user(username="decision-tool-reader")
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Prepare review",
            project="Research",
            estimated_minutes=45,
            due_at=datetime(2026, 7, 17, 12, tzinfo=UTC),
        )
    )
    TaskExecutionSignalService.record(
        RecordExecutionSignalCommand(
            user=user,
            task_id=task.pk,
            signal_type="started",
            occurred_at=datetime(2026, 7, 17, 7, tzinfo=UTC),
            idempotency_key="decision-tool-started",
        )
    )
    TaskExecutionSignalService.record(
        RecordExecutionSignalCommand(
            user=user,
            task_id=task.pk,
            signal_type="paused",
            occurred_at=datetime(2026, 7, 17, 7, 30, tzinfo=UTC),
            idempotency_key="decision-tool-paused",
        )
    )
    CalendarSyncService.create_connection(
        user=user,
        provider_name="ics",
        account_reference="private-account-reference",
        calendar_id="private-calendar-id",
        calendar_name="Read-only calendar",
        timezone_name="Asia/Shanghai",
    )
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "recommend_task_duration",
                        "args": {"task_id": str(task.pk)},
                        "id": "duration-read-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_capacity_forecast",
                        "args": {
                            "range_start": "2026-07-17T01:00:00Z",
                            "range_end": "2026-07-17T13:00:00Z",
                        },
                        "id": "capacity-read-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_task_execution_summary",
                        "args": {"task_id": str(task.pk)},
                        "id": "execution-read-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "list_calendar_sync_status",
                        "args": {},
                        "id": "calendar-sync-read-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="The recommendation and capacity are based on saved facts."),
        ]
    )
    agent = build_time_steward_agent(model=model, store=InMemoryStore())

    result = agent.invoke(
        {"messages": [HumanMessage(content="How long will this take, and can it fit today?")]},
        context=context(user, read_only=True),
    )

    payloads = {
        message.name: json.loads(str(message.content))
        for message in result["messages"]
        if isinstance(message, ToolMessage)
    }
    assert payloads["recommend_task_duration"]["task_id"] == str(task.pk)
    assert payloads["recommend_task_duration"]["recommended_minutes"] == 45
    assert "fallback_reason" in payloads["recommend_task_duration"]
    assert payloads["get_capacity_forecast"]["unplanned_minutes"] == 45
    assert payloads["get_capacity_forecast"]["risk"] in {
        "within_capacity",
        "tight",
        "over_capacity",
    }
    assert isinstance(payloads["get_capacity_forecast"]["reason_codes"], list)
    assert payloads["get_task_execution_summary"]["active_seconds"] == 30 * 60
    assert payloads["get_task_execution_summary"]["evidence_status"] == "complete"
    assert payloads["list_calendar_sync_status"] == [
        {
            "connection_id": payloads["list_calendar_sync_status"][0]["connection_id"],
            "provider_name": "ics",
            "calendar_name": "Read-only calendar",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "status": "ready",
            "last_synced_at": None,
            "last_error": "",
        }
    ]
    assert "private-account-reference" not in str(payloads["list_calendar_sync_status"])
    assert "record_task_duration_feedback" not in model.bound_tool_names


@pytest.mark.django_db(transaction=True)
def test_agent_records_duration_feedback_with_trusted_segment_and_idempotency() -> None:
    user = User.objects.create_user(username="decision-tool-writer")
    task = TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="Prepare review",
            project="Research",
            estimated_minutes=45,
        )
    )
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "record_task_duration_feedback",
                        "args": {"task_id": str(task.pk), "action": "too_short"},
                        "id": "duration-feedback-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Feedback recorded."),
        ]
    )
    agent = build_time_steward_agent(model=model, store=InMemoryStore())

    result = agent.invoke(
        {"messages": [HumanMessage(content="That estimate was too short.")]},
        context=context(user),
    )

    message = next(
        item
        for item in result["messages"]
        if isinstance(item, ToolMessage) and item.name == "record_task_duration_feedback"
    )
    payload = json.loads(str(message.content))
    feedback = TimeDecisionFeedback.objects.get(user=user)
    assert payload["feedback_id"] == str(feedback.pk)
    assert feedback.action == "too_short"
    assert feedback.source == "agent"
    assert feedback.value["segment"] == "project:research"
    assert feedback.idempotency_key.startswith("agent:")


@pytest.mark.django_db(transaction=True)
def test_fixed_eval_command_executes_and_checks_real_trajectories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = json.loads(
        (Path(__file__).parent / "fixtures" / "time_steward_eval.json").read_text(encoding="utf-8")
    )
    trajectories = []
    for case in cases:
        turns = case.get("turns", [{"prompt": case.get("prompt", "")}])
        expectations = case.get("expected_relative_specs", [])
        for turn_index, _turn in enumerate(turns):
            tool_calls = []
            for index, name in enumerate(case["required_tools"]):
                args: dict[str, Any] = {}
                if name == "mutate_events" and expectations:
                    args = {
                        "operations": [
                            {
                                "action": "create",
                                "time": {
                                    "kind": "relative",
                                    "duration_minutes": 60,
                                    **expectations[turn_index],
                                },
                            }
                        ]
                    }
                tool_calls.append(
                    {
                        "name": name,
                        "args": args,
                        "id": f"{case['id']}-{turn_index}-{index}",
                        "type": "tool_call",
                    }
                )
            trajectories.append(
                {
                    "messages": [
                        AIMessage(content="", tool_calls=tool_calls),
                        AIMessage(content="done"),
                    ]
                }
            )
    fake_agent = MagicMock()
    fake_agent.invoke.side_effect = trajectories
    monkeypatch.setattr(
        "apps.agents.management.commands.evaluate_time_steward.build_chat_model",
        MagicMock(),
    )
    monkeypatch.setattr(
        "apps.agents.management.commands.evaluate_time_steward.build_time_steward_agent",
        lambda **_kwargs: fake_agent,
    )
    output = StringIO()

    call_command("evaluate_time_steward", stdout=output)

    expected_turn_count = sum(len(case.get("turns", [case])) for case in cases)
    assert fake_agent.invoke.call_count == expected_turn_count
    assert f"Time Steward eval completed: {len(cases)}/{len(cases)} case(s) passed" in output.getvalue()


@pytest.mark.django_db
def test_eval_usage_metrics_report_token_coverage() -> None:
    LLMCallAudit.objects.create(
        request_id="eval-request-1",
        component="time_steward",
        model_name="test-model",
        status="completed",
        usage_source="provider",
        input_tokens=80,
        output_tokens=20,
        total_tokens=100,
        duration_ms=10,
    )
    LLMCallAudit.objects.create(
        request_id="eval-request-2",
        component="time_steward",
        model_name="test-model",
        status="completed",
        usage_source="unavailable",
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        duration_ms=10,
    )
    LLMCallAudit.objects.create(
        request_id="eval-request-1",
        component="briefing",
        model_name="test-model",
        status="completed",
        usage_source="provider",
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        duration_ms=10,
    )

    assert AgentEvalCommand._usage_for_requests(["eval-request-1", "eval-request-2"]) == {
        "model_call_count": 2,
        "completed_model_call_count": 2,
        "total_tokens": 100,
        "token_call_coverage": 0.5,
    }


def test_temporal_eval_compares_equivalent_time_formats() -> None:
    errors = AgentEvalCommand._temporal_expectation_errors(
        {"expected_relative_specs": [{"offset": 1, "unit": "day", "local_time": "09:00:00"}]},
        [
            {
                "name": "mutate_events",
                "succeeded": True,
                "args": {
                    "operations": [
                        {
                            "action": "create",
                            "time": {
                                "kind": "relative",
                                "offset": 1,
                                "unit": "day",
                                "local_time": "09:00",
                            },
                        }
                    ]
                },
            }
        ],
    )

    assert errors == []
