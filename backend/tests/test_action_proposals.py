from collections.abc import Callable, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
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

from apps.action_proposals.models import ActionProposalStatus
from apps.action_proposals.services import (
    ActionProposalService,
    ProposalConflictError,
)
from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.context import RuntimeContext
from apps.conversations.execution import execute_agent_run, resume_agent_run
from apps.conversations.models import AgentRunStatus
from apps.conversations.services import AgentRunService, ConversationService, StartRunCommand
from apps.events.models import CalendarEvent, CalendarEventStatus
from apps.events.services import CreateEventCommand, EventService
from apps.preferences.services import UserPreferenceService
from apps.preferences.snapshots import PlanningPreferencesSnapshot
from apps.reminders.models import ReminderStatus
from apps.reminders.services import CreateReminderCommand, ReminderService
from apps.tasks.models import TaskStatus
from apps.tasks.services import CreateTaskCommand, TaskService


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
                            "start_at": "2026-07-20T07:00:00Z",
                            "end_at": "2026-07-20T08:00:00Z",
                            "timezone": "Asia/Shanghai",
                        }
                    ]
                },
                "id": "mutate-events-hitl-1",
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
                        "start_at": "2026-07-25T10:00:00+08:00",
                        "end_at": "2026-07-25T10:30:00+08:00",
                        "timezone": "Asia/Shanghai",
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
    assert proposal.display_context["occurrences"][1]["start_at"] == "2026-07-26T10:00:00+08:00"


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

    decision = ActionProposalService.decide(
        user=user,
        proposal_id=proposal.pk,
        expected_version=proposal.version,
        decision="edit",
        decision_idempotency_key=uuid4(),
        edited_payload={
            "operations": [
                {**proposal.action_payload["operations"][0], "title": "已编辑的项目评审"}
            ]
        },
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
            _event_tool_call(),
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
    assert CalendarEvent.objects.get().title == "项目评审"
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
                                "start_at": "2026-07-20T07:30:00Z",
                                "end_at": "2026-07-20T08:30:00Z",
                                "timezone": "Asia/Shanghai",
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
    with pytest.raises(ProposalConflictError, match="still conflicts"):
        ActionProposalService.decide(
            user=user,
            proposal_id=proposal.pk,
            expected_version=proposal.version,
            decision="approve",
            decision_idempotency_key=uuid4(),
        )


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
                                "start_at": "2026-07-20T07:00:00Z",
                                "end_at": "2026-07-20T08:00:00Z",
                                "timezone": "Asia/Shanghai",
                            },
                            {
                                "action": "create",
                                "title": "Second interview prep",
                                "start_at": "2026-07-20T07:30:00Z",
                                "end_at": "2026-07-20T08:30:00Z",
                                "timezone": "Asia/Shanghai",
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
            "source": "same_mutation_batch",
        }
    ]
    with pytest.raises(ProposalConflictError, match="still conflicts"):
        ActionProposalService.decide(
            user=user,
            proposal_id=proposal.pk,
            expected_version=proposal.version,
            decision="approve",
            decision_idempotency_key=uuid4(),
        )
