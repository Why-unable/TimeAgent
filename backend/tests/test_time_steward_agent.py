import asyncio
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

from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.context import RuntimeContext
from apps.agents.middleware import (
    TemporalContextMiddleware,
    ToolPolicyMiddleware,
    _hitl_when,
    build_time_steward_middleware,
)
from apps.agents.tools import READ_ONLY_TOOLS, TIME_STEWARD_TOOLS, WRITE_TOOLS
from apps.conversations.models import AgentRunStatus, ToolCallAudit, ToolCallStatus
from apps.conversations.services import AgentRunService, ConversationService, StartRunCommand
from apps.events.services import CreateEventCommand, EventService
from apps.preferences.snapshots import PlanningPreferencesSnapshot
from apps.tasks.models import Task
from apps.tasks.services import TaskService
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
    assert str(historical_ai.content).startswith("[Historical assistant response.")
    assert historical_ai.tool_calls == []
    assert all(
        not (isinstance(message, ToolMessage) and message.name == "get_current_datetime")
        for message in model_messages
    )
    assert model_messages[-1].content == "Then schedule it tomorrow."

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
        "start_at": "2026-07-18T10:00:00+08:00",
        "end_at": "2026-07-18T11:00:00+08:00",
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
        "start_at": "2026-07-18T10:30:00+08:00",
        "end_at": "2026-07-18T11:30:00+08:00",
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


@pytest.mark.django_db(transaction=True)
def test_async_tool_failure_is_audited_and_emitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_task",
                        "args": {"title": "失败任务"},
                        "id": "create-task-failure",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )

    def fail_create(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(TaskService, "create_task", fail_create)
    agent = build_time_steward_agent(model=model)

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(
            agent.ainvoke(
                {"messages": [HumanMessage(content="创建失败任务")]},
                context=context(user, agent_run_id=str(run.pk)),
            )
        )

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
    }


@pytest.mark.django_db(transaction=True)
def test_fixed_eval_command_executes_and_checks_real_trajectories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = json.loads(
        (Path(__file__).parent / "fixtures" / "time_steward_eval.json").read_text(encoding="utf-8")
    )
    trajectories = [
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": name,
                            "args": {},
                            "id": f"{case['id']}-{index}",
                            "type": "tool_call",
                        }
                        for index, name in enumerate(case["required_tools"])
                    ],
                ),
                AIMessage(content="done"),
            ]
        }
        for case in cases
    ]
    fake_agent = MagicMock()
    fake_agent.invoke.side_effect = trajectories
    monkeypatch.setattr(
        "apps.agents.management.commands.evaluate_time_steward.build_chat_model",
        MagicMock(),
    )
    monkeypatch.setattr(
        "apps.agents.management.commands.evaluate_time_steward.build_time_steward_agent",
        lambda model: fake_agent,
    )
    output = StringIO()

    call_command("evaluate_time_steward", stdout=output)

    assert fake_agent.invoke.call_count == len(cases)
    assert f"Time Steward eval passed: {len(cases)} case(s)" in output.getvalue()
