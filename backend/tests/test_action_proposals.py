import json
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from apps.action_proposals.models import ActionProposal, ActionProposalStatus
from apps.action_proposals.risk_policy import HIGH_RISK_TOOL_POLICIES
from apps.action_proposals.services import (
    ACTION_TITLES,
    ActionProposalService,
    ProposalConflictError,
)
from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.context import RuntimeContext
from apps.conversations.execution import execute_agent_run, resume_agent_run
from apps.conversations.models import AgentRunStatus
from apps.conversations.services import AgentRunService, ConversationService, StartRunCommand
from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.events.services import CreateEventCommand, EventService, UpdateEventCommand
from apps.preferences.services import UserPreferenceService
from apps.preferences.snapshots import PlanningPreferencesSnapshot
from apps.reminders.models import ReminderStatus
from apps.reminders.services import CreateReminderCommand, ReminderService
from apps.tasks.models import TaskStatus
from apps.tasks.services import CreateTaskCommand, TaskService
from apps.time_memory.models import (
    MemoryProposal,
    MemoryProposalStatus,
    SemanticMemory,
    SemanticMemorySource,
    SemanticMemoryStatus,
)


def test_every_high_risk_action_has_a_localized_presentation_title() -> None:
    assert set(HIGH_RISK_TOOL_POLICIES) <= set(ACTION_TITLES)
    assert all(
        ACTION_TITLES[name] and name not in ACTION_TITLES[name] for name in HIGH_RISK_TOOL_POLICIES
    )


class ScriptedModel(BaseChatModel):
    responses: list[AIMessage]
    response_index: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-hitl-test"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        del tools, tool_choice, kwargs
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


def _setup_run(user: User) -> tuple[Any, RuntimeContext, RunnableConfig]:
    conversation = ConversationService.create(user=user)
    run = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="hitl-request",
            message="明天下午三点创建项目评审日程",
            anchor_at=datetime(2026, 7, 19, 8, tzinfo=UTC),
            anchor_timezone="Asia/Shanghai",
        )
    )
    run = AgentRunService.mark_running(run)
    context = RuntimeContext(
        user_id=str(user.pk),
        request_id=run.request_id,
        timezone="Asia/Shanghai",
        locale="zh-CN",
        current_datetime=datetime(2026, 7, 19, 8, tzinfo=UTC),
        trigger_type="user_message",
        conversation_id=str(conversation.pk),
        agent_run_id=str(run.pk),
        actor=user,
        planning_preferences=PlanningPreferencesSnapshot(
            require_event_creation_approval=True,
            require_event_cancellation_approval=True,
        ),
    )
    config: RunnableConfig = {"configurable": {"thread_id": str(conversation.pk)}}
    return run, context, config


@pytest.mark.django_db
def test_reminder_update_review_context_shows_each_proposed_change() -> None:
    user = User.objects.create_user(username="hitl-reminder-update-review")
    run, runtime_context, _ = _setup_run(user)
    reminder = ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title="提交周报",
            trigger_at=datetime(2026, 7, 20, 7, tzinfo=UTC),
            current_time=runtime_context.current_datetime,
            timezone="Asia/Shanghai",
            deduplication_key="hitl-reminder-update-review",
        )
    )

    display_context = ActionProposalService._display_context(
        run=run,
        tool_name="update_reminder",
        args={
            "reminder_id": str(reminder.pk),
            "expected_version": reminder.version,
            "title": "提交周报初稿",
            "trigger_at": "2026-07-20T08:00:00+00:00",
            "timezone": "Asia/Shanghai",
            "channel": "email",
        },
        allowed_decisions=["approve", "edit", "reject"],
        position=0,
    )

    review_item = display_context["review_items"][0]
    assert display_context["review_complete"] is True
    assert display_context["action_summary"] == "将修改提醒「提交周报」。"
    assert review_item["title"] == "提交周报初稿"
    assert review_item["start_at"] == reminder.trigger_at.isoformat()
    assert review_item["proposed_start_at"] == "2026-07-20T08:00:00+00:00"
    assert "标题：提交周报 → 提交周报初稿" in review_item["detail"]
    assert "通知方式：站内 → 邮件" in review_item["detail"]


@pytest.mark.django_db
def test_reminder_target_review_context_resolves_old_and_new_targets() -> None:
    user = User.objects.create_user(username="hitl-reminder-target-review")
    run, runtime_context, _ = _setup_run(user)
    reminder = ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title="准备材料提醒",
            trigger_at=datetime(2026, 7, 20, 7, tzinfo=UTC),
            current_time=runtime_context.current_datetime,
            timezone="Asia/Shanghai",
            deduplication_key="hitl-reminder-target-review",
        )
    )
    task = TaskService.create_task(
        CreateTaskCommand(user=user, title="准备答辩材料", source="agent")
    )

    display_context = ActionProposalService._display_context(
        run=run,
        tool_name="set_reminder_target",
        args={
            "reminder_id": str(reminder.pk),
            "expected_version": reminder.version,
            "target_type": "task",
            "target_id": str(task.pk),
        },
        allowed_decisions=["approve", "edit", "reject"],
        position=0,
    )
    review_item = display_context["review_items"][0]

    assert display_context["review_complete"] is True
    assert display_context["action_summary"] == "将更改提醒「准备材料提醒」关联的对象。"
    assert "关联对象：独立提醒 → 任务「准备答辩材料」" in review_item["detail"]


@pytest.mark.django_db
def test_reminder_target_review_context_fails_closed_when_target_is_missing() -> None:
    user = User.objects.create_user(username="hitl-reminder-target-missing")
    run, runtime_context, _ = _setup_run(user)
    reminder = ReminderService.create_reminder(
        CreateReminderCommand(
            user=user,
            title="准备材料提醒",
            trigger_at=datetime(2026, 7, 20, 7, tzinfo=UTC),
            current_time=runtime_context.current_datetime,
            timezone="Asia/Shanghai",
            deduplication_key="hitl-reminder-target-missing",
        )
    )

    display_context = ActionProposalService._display_context(
        run=run,
        tool_name="set_reminder_target",
        args={
            "reminder_id": str(reminder.pk),
            "expected_version": reminder.version,
            "target_type": "task",
            "target_id": str(uuid4()),
        },
        allowed_decisions=["approve", "edit", "reject"],
        position=0,
    )

    assert display_context["review_complete"] is False
    assert "任务（详情暂不可用）" in display_context["review_items"][0]["detail"]


def _event_tool_call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "mutate_events",
                "args": {
                    "operations": [
                        {
                            "action": "create",
                            "title": "项目评审",
                            "time": {
                                "kind": "absolute",
                                "start_at": "2026-07-20T07:00:00Z",
                                "end_at": "2026-07-20T08:00:00Z",
                            },
                        }
                    ]
                },
                "id": "mutate-events-hitl-1",
                "type": "tool_call",
            }
        ],
    )


def _remember_memory_tool_call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "remember_time_preference",
                "args": {
                    "category": "scheduling_preference",
                    "key": "friday_afternoon_meetings",
                    "value": {"avoid": True},
                },
                "id": "remember-memory-hitl-1",
                "type": "tool_call",
            }
        ],
    )


def _update_memory_tool_call(memory_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "update_time_preference",
                "args": {
                    "memory_id": memory_id,
                    "value": {"period": "afternoon"},
                },
                "id": "update-memory-hitl-1",
                "type": "tool_call",
            }
        ],
    )


def _relative_event_tool_call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "mutate_events",
                "args": {
                    "operations": [
                        {
                            "action": "create",
                            "title": "项目评审",
                            "time": {
                                "kind": "relative",
                                "offset": 1,
                                "unit": "day",
                                "source_text": "明天下午三点",
                                "local_time": "15:00:00",
                                "duration_minutes": 60,
                            },
                        }
                    ]
                },
                "id": "mutate-events-relative-hitl-1",
                "type": "tool_call",
            }
        ],
    )


def _conflict_check_tool_call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "detect_conflicts",
                "args": {
                    "start_at": "2026-07-20T07:00:00Z",
                    "end_at": "2026-07-20T08:00:00Z",
                },
                "id": "detect-conflicts-before-hitl",
                "type": "tool_call",
            }
        ],
    )


@pytest.mark.django_db
def test_recurring_event_proposal_includes_each_occurrence_preview() -> None:
    user = User.objects.create_user(username="recurring-preview")
    run, _, _ = _setup_run(user)
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value={
            "action_requests": [
                {
                    "name": "create_recurring_event",
                    "args": {
                        "title": "每日学习",
                        "time": {
                            "kind": "absolute",
                            "start_at": "2026-07-25T10:00:00+08:00",
                            "end_at": "2026-07-25T10:30:00+08:00",
                        },
                        "frequency": "daily",
                        "interval": 1,
                        "occurrence_count": 3,
                    },
                }
            ],
            "review_configs": [
                {
                    "action_name": "create_recurring_event",
                    "allowed_decisions": ["approve", "edit", "reject"],
                }
            ],
        },
    )[0]

    assert proposal.display_context["is_recurring"] is True
    assert proposal.display_context["conflict_check"] == "completed"
    assert proposal.display_context["impact_scope"] == "Creates 3 recurring calendar events"
    assert [item["index"] for item in proposal.display_context["occurrences"]] == [1, 2, 3]
    assert proposal.display_context["occurrences"][1]["start_at"] == "2026-07-26T02:00:00+00:00"


@pytest.mark.django_db(transaction=True)
def test_high_risk_tool_never_executes_before_edited_approval() -> None:
    user = User.objects.create_user(username="hitl-user")
    run, context, config = _setup_run(user)
    agent = build_time_steward_agent(
        model=ScriptedModel(responses=[_event_tool_call(), AIMessage(content="日程已创建。")]),
        checkpointer=InMemorySaver(),
    )

    interrupted = agent.invoke(
        {"messages": [HumanMessage(content=run.input_message)]},
        config=config,
        context=context,
    )

    assert CalendarEvent.objects.count() == 0
    interrupt_value = interrupted["__interrupt__"][0].value
    proposals = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value=interrupt_value,
    )
    proposal = proposals[0]
    assert proposal.status == ActionProposalStatus.AWAITING_APPROVAL
    resolved_operation = proposal.display_context["resolved_operations"][0]
    edited_operation = {
        key: value
        for key, value in resolved_operation.items()
        if key
        not in {"display_title", "existing_start_at", "existing_end_at", "display_task_title"}
    }
    edited_operation["title"] = "已编辑的项目评审"
    assert "display_title" not in edited_operation

    decision = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="edit",
        decision_idempotency_key=uuid4(),
        edited_payload={"operations": [edited_operation]},
    )
    assert decision.resume_ready
    resume_payload = ActionProposalService.resume_payload(run.pk)
    ActionProposalService.mark_resumed(run.pk)
    completed = agent.invoke(Command(resume=resume_payload), config=config, context=context)

    assert completed["messages"][-1].content == "日程已创建。"
    assert CalendarEvent.objects.get().title == "已编辑的项目评审"
    proposal.refresh_from_db()
    assert proposal.status == ActionProposalStatus.EXECUTED
    assert "已编辑的项目评审" in str(proposal.execution_result)


@pytest.mark.django_db
def test_edit_stays_pending_when_fresh_review_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User.objects.create_user(username="proposal-edit-incomplete-review")
    run, _, _ = _setup_run(user)
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value={
            "action_requests": [
                {"name": "mutate_events", "args": _event_tool_call().tool_calls[0]["args"]}
            ],
            "review_configs": [
                {"action_name": "mutate_events", "allowed_decisions": ["approve", "edit", "reject"]}
            ],
        },
    )[0]
    version_before_decision = proposal.version
    incomplete_context = {
        "allowed_decisions": ["approve", "edit", "reject"],
        "review_complete": False,
        "review_items": [],
        "conflict_check": "unavailable_until_arguments_are_valid",
        "conflicts": [],
    }
    monkeypatch.setattr(
        ActionProposalService,
        "_display_context",
        staticmethod(lambda **_kwargs: incomplete_context),
    )

    decision = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="edit",
        decision_idempotency_key=uuid4(),
        edited_payload={"operations": [{"action": "create", "title": "不完整预览"}]},
    )

    assert not decision.resume_ready
    assert decision.proposal.status == ActionProposalStatus.AWAITING_APPROVAL
    assert decision.proposal.version == version_before_decision + 1
    assert decision.proposal.action_payload == proposal.action_payload
    assert decision.proposal.display_context == incomplete_context
    assert decision.proposal.decision_type == "edit"


@pytest.mark.django_db(transaction=True)
def test_reschedule_task_waits_for_approval_and_applies_expected_version() -> None:
    user = User.objects.create_user(username="hitl-reschedule-task")
    task = TaskService.create_task(CreateTaskCommand(user=user, title="Prepare review"))
    run, base_context, config = _setup_run(user)
    message = "把 Prepare review 任务改到 7 月 22 日上午十点"
    run.input_message = message
    run.save(update_fields=["input_message"])
    context = replace(base_context, input_message=message)
    planned_start = datetime(2026, 7, 22, 2, tzinfo=UTC)
    planned_end = datetime(2026, 7, 22, 3, tzinfo=UTC)
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "reschedule_task",
                        "args": {
                            "task_id": str(task.pk),
                            "planned_start_at": planned_start.isoformat(),
                            "planned_end_at": planned_end.isoformat(),
                            "expected_version": task.version,
                        },
                        "id": "reschedule-task-hitl-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="任务时间已更新。"),
        ]
    )
    agent = build_time_steward_agent(model=model, checkpointer=InMemorySaver())

    interrupted = agent.invoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
        context=context,
    )

    task.refresh_from_db()
    assert task.planned_start_at is None
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value=interrupted["__interrupt__"][0].value,
    )[0]
    assert proposal.status == ActionProposalStatus.AWAITING_APPROVAL
    decision = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )
    assert decision.resume_ready
    resume_payload = ActionProposalService.resume_payload(run.pk)
    ActionProposalService.mark_resumed(run.pk)
    completed = agent.invoke(Command(resume=resume_payload), config=config, context=context)

    task.refresh_from_db()
    proposal.refresh_from_db()
    assert completed["messages"][-1].content == "任务时间已更新。"
    assert task.planned_start_at == planned_start
    assert task.planned_end_at == planned_end
    assert proposal.status == ActionProposalStatus.EXECUTED


@pytest.mark.django_db(transaction=True)
def test_rejected_high_risk_tool_resumes_without_execution() -> None:
    user = User.objects.create_user(username="hitl-reject")
    run, context, config = _setup_run(user)
    agent = build_time_steward_agent(
        model=ScriptedModel(responses=[_event_tool_call(), AIMessage(content="已取消创建日程。")]),
        checkpointer=InMemorySaver(),
    )
    interrupted = agent.invoke(
        {"messages": [HumanMessage(content=run.input_message)]},
        config=config,
        context=context,
    )
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value=interrupted["__interrupt__"][0].value,
    )[0]
    ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="reject",
        decision_idempotency_key=uuid4(),
        reason="时间不合适",
    )
    resume_payload = ActionProposalService.resume_payload(run.pk)
    ActionProposalService.mark_resumed(run.pk)
    completed = agent.invoke(Command(resume=resume_payload), config=config, context=context)

    assert completed["messages"][-1].content == "已取消创建日程。"
    assert CalendarEvent.objects.count() == 0
    proposal.refresh_from_db()
    assert proposal.status == ActionProposalStatus.REJECTED


@override_settings(
    TIME_MEMORY_AGENT_WRITE_TOOLS_ENABLED=True,
    TIME_MEMORY_AGENT_INLINE_APPROVAL_ENABLED=True,
)
@pytest.mark.django_db(transaction=True)
def test_memory_tool_applies_once_after_inline_approval_and_same_run_resume() -> None:
    user = User.objects.create_user(username="memory-hitl-approve")
    preference = UserPreferenceService.get_or_create_for_user(user)
    preference.time_memory_enabled = True
    preference.time_memory_allow_generation = True
    preference.save(update_fields=["time_memory_enabled", "time_memory_allow_generation"])
    run, context, config = _setup_run(user)
    run.input_message = "请记住以后周五下午不要安排会议"
    run.save(update_fields=["input_message"])
    agent = build_time_steward_agent(
        model=ScriptedModel(
            responses=[_remember_memory_tool_call(), AIMessage(content="已记住该偏好。")]
        ),
        checkpointer=InMemorySaver(),
    )

    interrupted = agent.invoke(
        {"messages": [HumanMessage(content=run.input_message)]},
        config=config,
        context=context,
    )

    assert SemanticMemory.objects.count() == 0
    assert MemoryProposal.objects.count() == 0
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value=interrupted["__interrupt__"][0].value,
    )[0]
    assert proposal.display_context["memory_target_id"] is None
    assert proposal.display_context["proposed_memory_value"] == {"avoid": True}

    ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )
    resume_payload = ActionProposalService.resume_payload(run.pk)
    ActionProposalService.mark_resumed(run.pk)
    completed = agent.invoke(Command(resume=resume_payload), config=config, context=context)

    memory = SemanticMemory.objects.get(user=user, status=SemanticMemoryStatus.ACTIVE)
    memory_proposal = MemoryProposal.objects.get(user=user)
    proposal.refresh_from_db()
    assert memory.value == {"avoid": True}
    assert memory.source_type == SemanticMemorySource.EXPLICIT_USER
    assert memory_proposal.status == MemoryProposalStatus.APPLIED
    assert proposal.status == ActionProposalStatus.EXECUTED
    assert proposal.execution_result is not None
    execution_result = json.loads(proposal.execution_result["content"])
    assert execution_result["requires_confirmation"] is False
    assert completed["messages"][-1].content == "已记住该偏好。"


@pytest.mark.django_db
def test_memory_execution_approval_cannot_be_reused_with_different_arguments() -> None:
    user = User.objects.create_user(username="memory-hitl-arguments")
    run, _, _ = _setup_run(user)
    arguments = {
        "category": "scheduling_preference",
        "key": "friday_afternoon_meetings",
        "value": {"avoid": True},
    }
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value={
            "action_requests": [
                {
                    "name": "remember_time_preference",
                    "args": arguments,
                }
            ],
            "review_configs": [
                {
                    "action_name": "remember_time_preference",
                    "allowed_decisions": ["approve", "reject"],
                }
            ],
        },
    )[0]
    ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )
    ActionProposalService.mark_resumed(run.pk)
    ActionProposalService.bind_tool_call(
        run_id=str(run.pk),
        tool_call_id="remember-memory-bound-1",
        tool_name="remember_time_preference",
        arguments=arguments,
    )
    ActionProposalService.mark_executing(
        run_id=str(run.pk),
        tool_call_id="remember-memory-bound-1",
    )

    with pytest.raises(ActionProposal.DoesNotExist):
        ActionProposalService.get_approved_tool_execution(
            user=user,
            run_id=str(run.pk),
            tool_call_id="remember-memory-bound-1",
            tool_name="remember_time_preference",
            arguments={**arguments, "value": {"avoid": False}},
        )


@override_settings(
    TIME_MEMORY_AGENT_WRITE_TOOLS_ENABLED=True,
    TIME_MEMORY_AGENT_INLINE_APPROVAL_ENABLED=True,
)
@pytest.mark.django_db(transaction=True)
def test_inline_memory_approval_is_invalidated_when_target_changes_before_resume() -> None:
    user = User.objects.create_user(username="memory-hitl-stale")
    preference = UserPreferenceService.get_or_create_for_user(user)
    preference.time_memory_enabled = True
    preference.time_memory_allow_generation = True
    preference.save(update_fields=["time_memory_enabled", "time_memory_allow_generation"])
    run, context, config = _setup_run(user)
    run.input_message = "把我的专注时间改成下午"
    run.save(update_fields=["input_message"])
    memory = SemanticMemory.objects.create(
        user=user,
        category="scheduling_preference",
        key="focus_period",
        value={"period": "morning"},
        source_type=SemanticMemorySource.EXPLICIT_USER,
        confidence=1,
    )
    agent = build_time_steward_agent(
        model=ScriptedModel(
            responses=[
                _update_memory_tool_call(str(memory.pk)),
                AIMessage(content="偏好在确认期间发生变化，请重新确认。"),
            ]
        ),
        checkpointer=InMemorySaver(),
    )
    interrupted = agent.invoke(
        {"messages": [HumanMessage(content=run.input_message)]},
        config=config,
        context=context,
    )
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value=interrupted["__interrupt__"][0].value,
    )[0]
    assert proposal.display_context["memory_target_id"] == str(memory.pk)
    assert proposal.display_context["memory_target_version"] == 1
    ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )
    memory.value = {"period": "evening"}
    memory.version = 2
    memory.save(update_fields=["value", "version", "updated_at"])
    resume_payload = ActionProposalService.resume_payload(run.pk)
    ActionProposalService.mark_resumed(run.pk)

    completed = agent.invoke(Command(resume=resume_payload), config=config, context=context)

    memory.refresh_from_db()
    proposal.refresh_from_db()
    assert memory.value == {"period": "evening"}
    assert MemoryProposal.objects.count() == 0
    assert proposal.status == ActionProposalStatus.FAILED
    assert "Memory changed after approval" in proposal.error
    assert completed["messages"][-1].content == "偏好在确认期间发生变化，请重新确认。"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("tool_name", ["mutate_events", "cancel_reminder", "cancel_task"])
def test_cancellation_tools_pause_before_side_effect_and_execute_only_after_approval(
    tool_name: str,
) -> None:
    user = User.objects.create_user(username=f"hitl-{tool_name}")
    run, context, config = _setup_run(user)
    run.input_message = f"请执行 {tool_name}"
    run.save(update_fields=["input_message"])

    target: Any
    arguments: dict[str, Any]
    cancelled_status: str
    if tool_name == "mutate_events":
        target = EventService.create_event(
            CreateEventCommand(
                user=user,
                title="待取消会议",
                start_at=datetime(2026, 7, 21, 7, tzinfo=UTC),
                end_at=datetime(2026, 7, 21, 8, tzinfo=UTC),
                timezone="Asia/Shanghai",
            )
        )
        arguments = {
            "operations": [
                {
                    "action": "cancel",
                    "event_id": str(target.pk),
                    "expected_version": target.version,
                }
            ]
        }
        cancelled_status = CalendarEventStatus.CANCELLED
    elif tool_name == "cancel_reminder":
        target = ReminderService.create_reminder(
            CreateReminderCommand(
                user=user,
                title="待取消提醒",
                trigger_at=datetime(2026, 7, 21, 7, tzinfo=UTC),
                current_time=context.current_datetime,
                timezone="Asia/Shanghai",
                deduplication_key=f"hitl-{tool_name}",
            )
        )
        arguments = {"reminder_id": str(target.pk)}
        cancelled_status = ReminderStatus.CANCELLED
    else:
        target = TaskService.create_task(
            CreateTaskCommand(user=user, title="待取消任务", source="agent")
        )
        arguments = {"task_id": str(target.pk)}
        cancelled_status = TaskStatus.CANCELLED

    initial_status = target.status
    tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": tool_name,
                "args": arguments,
                "id": f"{tool_name}-hitl-1",
                "type": "tool_call",
            }
        ],
    )
    agent = build_time_steward_agent(
        model=ScriptedModel(responses=[tool_call, AIMessage(content="撤销操作已执行。")]),
        checkpointer=InMemorySaver(),
    )

    interrupted = agent.invoke(
        {"messages": [HumanMessage(content=run.input_message)]},
        config=config,
        context=context,
    )

    target.refresh_from_db()
    assert target.status == initial_status
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value=interrupted["__interrupt__"][0].value,
    )[0]
    if tool_name == "mutate_events":
        assert proposal.display_context["object_name"] == "1 calendar operations"
        assert proposal.display_context["allowed_decisions"] == ["approve", "edit", "reject"]
    else:
        assert proposal.display_context["object_name"] == target.title
        assert proposal.display_context["allowed_decisions"] == ["approve", "reject"]

    ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )
    resume_payload = ActionProposalService.resume_payload(run.pk)
    ActionProposalService.mark_resumed(run.pk)
    completed = agent.invoke(Command(resume=resume_payload), config=config, context=context)

    target.refresh_from_db()
    proposal.refresh_from_db()
    assert target.status == cancelled_status
    assert proposal.status == ActionProposalStatus.EXECUTED
    assert completed["messages"][-1].content == "撤销操作已执行。"


@pytest.mark.django_db(transaction=True)
def test_production_outer_graph_run_pauses_and_resumes_same_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User.objects.create_user(username="outer-hitl")
    UserPreferenceService.update_for_user(user, {"require_event_creation_approval": True})
    run, _, _ = _setup_run(user)
    run.status = AgentRunStatus.PENDING
    run.started_at = None
    run.save(update_fields=["status", "started_at"])
    initial_task_id = "outer-initial-task"
    assert AgentRunService.reserve_execution_task(run, initial_task_id)
    persistence = type(
        "TestPersistence",
        (),
        {"checkpointer": InMemorySaver(), "store": InMemoryStore()},
    )()

    @contextmanager
    def fake_persistence() -> Any:
        yield persistence

    monkeypatch.setattr(
        "apps.conversations.execution.open_langgraph_persistence",
        fake_persistence,
    )
    model = ScriptedModel(
        responses=[
            _relative_event_tool_call(),
            AIMessage(content="已通过恢复流程创建日程。"),
        ]
    )

    waiting = execute_agent_run(
        run,
        actor=user,
        model=model,
        task_id=initial_task_id,
        now=datetime(2026, 7, 19, 8, tzinfo=UTC),
    )

    assert waiting.status == AgentRunStatus.WAITING_APPROVAL
    assert CalendarEvent.objects.count() == 0
    proposal = waiting.action_proposals.get()
    assert proposal.action_type == "mutate_events"
    assert proposal.tool_call_id.startswith("pending:")
    ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )
    resume_task_id = "outer-resume-task"
    assert AgentRunService.reserve_resume_task(waiting, resume_task_id)

    completed = resume_agent_run(
        waiting,
        actor=user,
        model=model,
        task_id=resume_task_id,
        now=datetime(2026, 7, 19, 8, 1, tzinfo=UTC),
    )

    assert completed.status == AgentRunStatus.COMPLETED
    assert completed.final_response == "已通过恢复流程创建日程。"
    created_event = CalendarEvent.objects.get()
    assert created_event.title == "项目评审"
    assert created_event.start_at == datetime(2026, 7, 20, 7, tzinfo=UTC)
    assert completed.anchor_at == datetime(2026, 7, 19, 8, tzinfo=UTC)
    assert completed.anchor_timezone == "Asia/Shanghai"
    temporal_event = completed.events.get(event_type="temporal.resolved")
    assert temporal_event.payload["resolved_at"] == "2026-07-20T07:00:00+00:00"
    proposal.refresh_from_db()
    assert proposal.status == ActionProposalStatus.EXECUTED


@pytest.mark.django_db
def test_edit_reject_expiry_concurrency_and_idempotency() -> None:
    user = User.objects.create_user(username="proposal-decisions")
    run, _, _ = _setup_run(user)
    payload = {
        "action_requests": [
            {"name": "mutate_events", "args": _event_tool_call().tool_calls[0]["args"]}
        ],
        "review_configs": [
            {"action_name": "mutate_events", "allowed_decisions": ["approve", "edit", "reject"]}
        ],
    }
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value=payload,
    )[0]
    operation_id = uuid4()
    edited = {"operations": [{**proposal.action_payload["operations"][0], "title": "编辑后的评审"}]}
    first = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=1,
        decision="edit",
        decision_idempotency_key=operation_id,
        edited_payload=edited,
    )
    replay = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=1,
        decision="edit",
        decision_idempotency_key=operation_id,
        edited_payload=edited,
    )
    assert first.proposal.pk == replay.proposal.pk
    assert replay.proposal.action_payload["operations"][0]["title"] == "编辑后的评审"

    with pytest.raises(ProposalConflictError):
        ActionProposalService.decide(
            user=user,
            proposal_id=proposal.pk,
            expected_version=1,
            decision="reject",
            decision_idempotency_key=uuid4(),
        )

    second_run, _, _ = _setup_run(user)
    expired = ActionProposalService.create_from_interrupt(
        run=second_run,
        interrupt_value=payload,
    )[0]
    expired.expires_at = timezone.now() - timedelta(seconds=1)
    expired.save(update_fields=["expires_at"])
    expired_decision = ActionProposalService.decide(
        user=user,
        proposal_id=expired.pk,
        expected_version=1,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )
    assert not expired_decision.resume_ready
    expired.refresh_from_db()
    assert expired.status == ActionProposalStatus.EXPIRED
    assert CalendarEvent.objects.count() == 0
    assert run.status == AgentRunStatus.RUNNING


@pytest.mark.django_db
def test_event_proposal_surfaces_conflict_and_cannot_be_approved() -> None:
    user = User.objects.create_user(username="proposal-conflict")
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Existing meeting",
            start_at=datetime(2026, 7, 20, 7, tzinfo=UTC),
            end_at=datetime(2026, 7, 20, 8, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )
    run, _, _ = _setup_run(user)
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value={
            "action_requests": [
                {
                    "name": "mutate_events",
                    "args": {
                        "operations": [
                            {
                                "action": "create",
                                "title": "Overlapping meeting",
                                "time": {
                                    "kind": "absolute",
                                    "start_at": "2026-07-20T07:30:00Z",
                                    "end_at": "2026-07-20T08:30:00Z",
                                },
                            }
                        ]
                    },
                }
            ],
            "review_configs": [
                {
                    "action_name": "mutate_events",
                    "allowed_decisions": ["approve", "edit", "reject"],
                }
            ],
        },
    )[0]

    assert proposal.display_context["conflict_check"] == "completed"
    assert proposal.display_context["conflicts"][0]["title"] == "Existing meeting"
    assert (
        proposal.display_context["conflicts"][0]["overlap_start_at"] == "2026-07-20T07:30:00+00:00"
    )
    assert proposal.display_context["conflicts"][0]["overlap_end_at"] == "2026-07-20T08:00:00+00:00"
    decision = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )
    assert not decision.resume_ready
    assert decision.proposal.status == ActionProposalStatus.AWAITING_APPROVAL
    assert decision.proposal.display_context["conflicts"][0]["title"] == "Existing meeting"
    assert decision.proposal.version == proposal.version + 1


@pytest.mark.django_db
def test_update_event_preview_uses_existing_times_for_null_partial_fields() -> None:
    user = User.objects.create_user(username="proposal-update-event-partial")
    event = EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Existing meeting",
            start_at=datetime(2026, 7, 20, 7, tzinfo=UTC),
            end_at=datetime(2026, 7, 20, 8, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )
    run, _, _ = _setup_run(user)

    display_context = ActionProposalService._display_context(
        run=run,
        tool_name="update_event",
        args={
            "event_id": str(event.pk),
            "expected_version": event.version,
            "title": "Renamed meeting",
            "start_at": None,
            "end_at": None,
        },
        allowed_decisions=["approve", "edit", "reject"],
        position=0,
    )

    assert display_context["review_complete"] is True
    assert display_context["conflict_check"] == "completed"
    assert display_context["proposed_start_at"] == event.start_at.isoformat()
    assert display_context["proposed_end_at"] == event.end_at.isoformat()
    assert display_context["review_items"][0]["title"] == "Renamed meeting"


@pytest.mark.django_db
def test_approval_rebases_stale_event_version_and_requires_a_second_confirmation() -> None:
    user = User.objects.create_user(username="proposal-stale-event-version")
    event = EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Existing meeting",
            start_at=datetime(2026, 10, 20, 7, tzinfo=UTC),
            end_at=datetime(2026, 10, 20, 8, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )
    run, _, _ = _setup_run(user)
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value={
            "action_requests": [
                {
                    "name": "mutate_events",
                    "args": {
                        "operations": [
                            {
                                "action": "update",
                                "event_id": str(event.pk),
                                "expected_version": event.version,
                                "title": "Renamed meeting",
                            }
                        ]
                    },
                }
            ],
            "review_configs": [
                {
                    "action_name": "mutate_events",
                    "allowed_decisions": ["approve", "edit", "reject"],
                }
            ],
        },
    )[0]
    assert proposal.display_context["stale_targets"] == []

    event = EventService.update_event(
        UpdateEventCommand(
            user=user,
            event_id=event.pk,
            expected_version=event.version,
            changes={"location": "Room B"},
        )
    )
    refresh_key = uuid4()
    first_decision = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="approve",
        decision_idempotency_key=refresh_key,
    )

    assert not first_decision.resume_ready
    assert first_decision.proposal.status == ActionProposalStatus.AWAITING_APPROVAL
    assert (
        first_decision.proposal.action_payload["operations"][0]["expected_version"] == event.version
    )
    assert (
        first_decision.proposal.display_context["stale_targets"][0]["current_version"]
        == event.version
    )
    assert "已有更新" in first_decision.proposal.display_context["review_notice"]
    assert first_decision.proposal.version == proposal.version + 1
    assert first_decision.proposal.decision_type == "approve"

    replayed_refresh = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="approve",
        decision_idempotency_key=refresh_key,
    )
    assert not replayed_refresh.resume_ready
    assert replayed_refresh.proposal.status == ActionProposalStatus.AWAITING_APPROVAL
    assert replayed_refresh.proposal.version == first_decision.proposal.version

    second_decision = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=first_decision.proposal.version,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )
    assert second_decision.resume_ready
    assert second_decision.proposal.status == ActionProposalStatus.APPROVED


@pytest.mark.django_db
def test_edit_rebases_stale_event_version_and_stays_pending_for_review() -> None:
    user = User.objects.create_user(username="proposal-stale-event-edit")
    event = EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Existing meeting",
            start_at=datetime(2026, 10, 20, 7, tzinfo=UTC),
            end_at=datetime(2026, 10, 20, 8, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )
    run, _, _ = _setup_run(user)
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value={
            "action_requests": [
                {
                    "name": "mutate_events",
                    "args": {
                        "operations": [
                            {
                                "action": "update",
                                "event_id": str(event.pk),
                                "expected_version": event.version,
                                "title": "Proposed title",
                            }
                        ]
                    },
                }
            ],
            "review_configs": [
                {
                    "action_name": "mutate_events",
                    "allowed_decisions": ["approve", "edit", "reject"],
                }
            ],
        },
    )[0]
    EventService.update_event(
        UpdateEventCommand(
            user=user,
            event_id=event.pk,
            expected_version=event.version,
            changes={"location": "Room C"},
        )
    )
    edited_payload = {
        "operations": [
            {
                **proposal.action_payload["operations"][0],
                "title": "Edited title",
            }
        ]
    }
    edit_key = uuid4()

    first_edit = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="edit",
        decision_idempotency_key=edit_key,
        edited_payload=edited_payload,
    )

    assert not first_edit.resume_ready
    assert first_edit.proposal.status == ActionProposalStatus.AWAITING_APPROVAL
    assert (
        first_edit.proposal.action_payload["operations"][0]["expected_version"] == event.version + 1
    )
    assert first_edit.proposal.action_payload["operations"][0]["title"] == "Edited title"
    assert "编辑期间已有更新" in first_edit.proposal.display_context["review_notice"]
    replayed_edit = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="edit",
        decision_idempotency_key=edit_key,
        edited_payload=edited_payload,
    )
    assert not replayed_edit.resume_ready
    assert replayed_edit.proposal.status == ActionProposalStatus.AWAITING_APPROVAL
    assert replayed_edit.proposal.version == first_edit.proposal.version

    confirmed = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=first_edit.proposal.version,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )
    assert confirmed.resume_ready
    assert confirmed.proposal.status == ActionProposalStatus.APPROVED


@pytest.mark.django_db
def test_approval_refreshes_conflicts_created_after_the_proposal() -> None:
    user = User.objects.create_user(username="proposal-stale-conflict")
    run, _, _ = _setup_run(user)
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value={
            "action_requests": [
                {
                    "name": "mutate_events",
                    "args": {
                        "operations": [
                            {
                                "action": "create",
                                "title": "Proposed meeting",
                                "time": {
                                    "kind": "absolute",
                                    "start_at": "2026-07-20T07:00:00Z",
                                    "end_at": "2026-07-20T08:00:00Z",
                                },
                            }
                        ]
                    },
                }
            ],
            "review_configs": [
                {
                    "action_name": "mutate_events",
                    "allowed_decisions": ["approve", "edit", "reject"],
                }
            ],
        },
    )[0]
    assert proposal.display_context["conflicts"] == []
    version_before_decision = proposal.version
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Added after proposal",
            start_at=datetime(2026, 7, 20, 7, 30, tzinfo=UTC),
            end_at=datetime(2026, 7, 20, 8, 30, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )

    decision = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )

    assert not decision.resume_ready
    assert decision.proposal.status == ActionProposalStatus.AWAITING_APPROVAL
    assert decision.proposal.display_context["conflicts"][0]["title"] == "Added after proposal"
    assert decision.proposal.version == version_before_decision + 1


@pytest.mark.django_db
def test_edit_refreshes_conflicts_created_after_the_proposal() -> None:
    user = User.objects.create_user(username="proposal-stale-edit-conflict")
    run, _, _ = _setup_run(user)
    args = {
        "operations": [
            {
                "action": "create",
                "title": "Proposed meeting",
                "time": {
                    "kind": "absolute",
                    "start_at": "2026-07-20T07:00:00Z",
                    "end_at": "2026-07-20T08:00:00Z",
                },
            }
        ],
    }
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value={
            "action_requests": [{"name": "mutate_events", "args": args}],
            "review_configs": [
                {"action_name": "mutate_events", "allowed_decisions": ["approve", "edit", "reject"]}
            ],
        },
    )[0]
    version_before_decision = proposal.version
    resolved_operation = proposal.display_context["resolved_operations"][0]
    edited_operation = {
        key: value
        for key, value in resolved_operation.items()
        if key
        not in {"display_title", "existing_start_at", "existing_end_at", "display_task_title"}
    }
    edited_operation["title"] = "Edited proposed meeting"
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="Added after proposal",
            start_at=datetime(2026, 7, 20, 7, 30, tzinfo=UTC),
            end_at=datetime(2026, 7, 20, 8, 30, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )

    decision = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="edit",
        decision_idempotency_key=uuid4(),
        edited_payload={"operations": [edited_operation]},
    )

    assert not decision.resume_ready
    assert decision.proposal.status == ActionProposalStatus.AWAITING_APPROVAL
    assert decision.proposal.display_context["conflicts"][0]["title"] == "Added after proposal"
    assert decision.proposal.version == version_before_decision + 1
    assert decision.proposal.action_payload == proposal.action_payload


@pytest.mark.django_db
def test_event_mutation_preflight_detects_overlap_inside_same_batch() -> None:
    user = User.objects.create_user(username="proposal-batch-conflict")
    run, _, _ = _setup_run(user)
    proposal = ActionProposalService.create_from_interrupt(
        run=run,
        interrupt_value={
            "action_requests": [
                {
                    "name": "mutate_events",
                    "args": {
                        "operations": [
                            {
                                "action": "create",
                                "title": "First interview prep",
                                "time": {
                                    "kind": "absolute",
                                    "start_at": "2026-07-20T07:00:00Z",
                                    "end_at": "2026-07-20T08:00:00Z",
                                },
                            },
                            {
                                "action": "create",
                                "title": "Second interview prep",
                                "time": {
                                    "kind": "absolute",
                                    "start_at": "2026-07-20T07:30:00Z",
                                    "end_at": "2026-07-20T08:30:00Z",
                                },
                            },
                        ]
                    },
                }
            ],
            "review_configs": [
                {
                    "action_name": "mutate_events",
                    "allowed_decisions": ["approve", "edit", "reject"],
                }
            ],
        },
    )[0]

    assert proposal.display_context["conflict_check"] == "completed"
    assert proposal.display_context["conflicts"] == [
        {
            "operation_index": 1,
            "conflicting_operation_index": 0,
            "title": "First interview prep",
            "start_at": "2026-07-20T07:00:00+00:00",
            "end_at": "2026-07-20T08:00:00+00:00",
            "overlap_start_at": "2026-07-20T07:30:00+00:00",
            "overlap_end_at": "2026-07-20T08:00:00+00:00",
            "source": "same_mutation_batch",
        }
    ]
    decision = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="approve",
        decision_idempotency_key=uuid4(),
    )
    assert decision.proposal.status == ActionProposalStatus.AWAITING_APPROVAL
    assert decision.proposal.display_context["conflicts"][0]["source"] == "same_mutation_batch"
