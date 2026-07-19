from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from langchain.tools import ToolRuntime
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.graph import END, START, StateGraph
from rest_framework.test import APIClient

from apps.agents.agents.time_steward import build_time_steward_agent
from apps.agents.context import RuntimeContext
from apps.agents.outer_graph import OuterGraphNodes, build_outer_graph
from apps.agents.routing import runtime_context_from_trigger
from apps.agents.state import AppState
from apps.agents.tools.handoff_tools import transfer_to_briefing
from apps.agents.triggers import TriggerEnvelope
from apps.briefings.models import BriefingRun, BriefingRunStatus
from apps.briefings.registry import BriefingRegistry, SectionContext
from apps.briefings.schemas import BriefingDraft, SectionResult
from apps.briefings.services import (
    BriefingDefinitionService,
    BriefingRunService,
    StartBriefingCommand,
)
from apps.briefings.workflow import briefing_workflow_node
from apps.conversations.models import Conversation, ConversationKind
from apps.conversations.services import AgentRunService, ConversationService, StartRunCommand
from apps.events.services import CreateEventCommand, EventService
from apps.tasks.services import CreateTaskCommand, TaskService


class HandoffChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "briefing-handoff-test"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> RunnableLambda[Any, Any]:
        del tools, tool_choice, kwargs
        return RunnableLambda(lambda _: self._response())

    def _response(self) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "transfer_to_briefing",
                    "args": {"request": "生成今天的简报", "target_date": "2026-07-19"},
                    "id": "handoff-outer-1",
                    "type": "tool_call",
                }
            ],
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=self._response())])


def _editor(_: object) -> dict[str, BriefingDraft]:
    return {
        "structured_response": BriefingDraft(
            title="今日简报",
            overview="今天的安排已经整理完成。",
            suggestions=["先完成最紧急的事项。"],
        )
    }


def _context(
    user: User,
    conversation_id: str,
    run_id: str,
    *,
    timezone: str = "Asia/Shanghai",
) -> RuntimeContext:
    return RuntimeContext(
        user_id=str(user.pk),
        request_id="briefing-test",
        timezone=timezone,
        locale="zh-CN",
        current_datetime=datetime(2026, 7, 19, 1, 0, tzinfo=UTC),
        trigger_type="manual_briefing",
        conversation_id=conversation_id,
        agent_run_id=run_id,
        actor=user,
    )


@pytest.mark.django_db(transaction=True)
def test_manual_briefing_collects_sections_persists_and_returns_ai_message() -> None:
    user = User.objects.create_user(username="briefing-user")
    EventService.create_event(
        CreateEventCommand(
            user=user,
            title="项目评审",
            start_at=datetime(2026, 7, 19, 2, 0, tzinfo=UTC),
            end_at=datetime(2026, 7, 19, 3, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )
    TaskService.create_task(
        CreateTaskCommand(
            user=user,
            title="提交报告",
            due_at=datetime(2026, 7, 19, 10, 0, tzinfo=UTC),
        )
    )
    definition = BriefingDefinitionService.default_for_user(user)
    conversation = ConversationService.create(
        user=user, title="手动简报", kind=ConversationKind.MANUAL_BRIEFING
    )
    run = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=uuid4(),
            request_id="briefing-test",
            message="手动生成每日简报",
            trigger_type="manual_briefing",
            trigger_payload={
                "briefing_definition_id": str(definition.pk),
                "target_date": "2026-07-19",
            },
            synthetic_input=True,
        )
    )
    builder = StateGraph(AppState, context_schema=RuntimeContext)

    def node(state: AppState, runtime: Any) -> dict[str, Any]:
        return briefing_workflow_node(
            state,
            runtime,
            editor=RunnableLambda(_editor),
        )

    builder.add_node("briefing", node)
    builder.add_edge(START, "briefing")
    builder.add_edge("briefing", END)
    graph = builder.compile()
    result = graph.invoke(
        {
            "messages": [HumanMessage(content=run.input_message)],
            "trigger_type": "manual_briefing",
            "trigger_payload": run.trigger_payload,
            "operation_id": str(run.operation_id),
        },
        context=_context(user, str(conversation.pk), str(run.pk)),
    )

    briefing_run = BriefingRun.objects.get(operation_id=run.operation_id)
    assert briefing_run.status == BriefingRunStatus.COMPLETED
    assert {item.section_key for item in briefing_run.section_runs.all()} == {
        "calendar",
        "news",
        "tasks",
        "weather",
    }
    assert all(item.status == "completed" for item in briefing_run.section_runs.all())
    assert isinstance(result["messages"][-1], AIMessage)
    assert "今日简报" in str(result["messages"][-1].content)


@pytest.mark.django_db
def test_briefing_inherits_runtime_timezone_when_definition_has_no_override() -> None:
    user = User.objects.create_user(username="briefing-timezone-user")
    definition = BriefingDefinitionService.default_for_user(user)
    definition = BriefingDefinitionService.save(
        user=user,
        definition=definition,
        name=definition.name,
        enabled_sections=["calendar", "tasks"],
    )
    operation_id = uuid4()

    run = BriefingRunService.start(
        StartBriefingCommand(
            user=user,
            operation_id=operation_id,
            trigger_type="manual_briefing",
            target_date=date(2026, 7, 19),
            timezone="Europe/London",
            definition_id=definition.pk,
        )
    )

    assert run.timezone == "Europe/London"


class FailingTaskSection:
    key = "tasks"

    def collect(self, *, user: User, context: SectionContext) -> SectionResult:
        del user, context
        raise TimeoutError("task source timeout")


@pytest.mark.django_db(transaction=True)
def test_single_section_failure_produces_partial_briefing() -> None:
    from apps.briefings.sections import CalendarBriefingSection

    user = User.objects.create_user(username="partial-briefing-user")
    definition = BriefingDefinitionService.default_for_user(user)
    definition = BriefingDefinitionService.save(
        user=user,
        definition=definition,
        name=definition.name,
        enabled_sections=["calendar", "tasks"],
    )
    conversation = ConversationService.create(user=user, kind=ConversationKind.MANUAL_BRIEFING)
    operation_id = uuid4()
    run = AgentRunService.start(
        StartRunCommand(
            conversation=conversation,
            operation_id=operation_id,
            request_id="partial-test",
            message="手动生成每日简报",
            trigger_type="manual_briefing",
            trigger_payload={
                "briefing_definition_id": str(definition.pk),
                "target_date": "2026-07-19",
            },
            synthetic_input=True,
        )
    )
    registry = BriefingRegistry.from_sections([CalendarBriefingSection(), FailingTaskSection()])
    builder = StateGraph(AppState, context_schema=RuntimeContext)

    def node(state: AppState, runtime: Any) -> dict[str, Any]:
        return briefing_workflow_node(
            state,
            runtime,
            registry=registry,
            editor=RunnableLambda(_editor),
        )

    builder.add_node("briefing", node)
    builder.add_edge(START, "briefing")
    builder.add_edge("briefing", END)
    result = builder.compile().invoke(
        {
            "messages": [HumanMessage(content=run.input_message)],
            "trigger_type": "manual_briefing",
            "trigger_payload": run.trigger_payload,
            "operation_id": str(operation_id),
        },
        context=_context(user, str(conversation.pk), str(run.pk)),
    )

    briefing_run = BriefingRun.objects.get(operation_id=operation_id)
    assert briefing_run.status == BriefingRunStatus.PARTIAL
    assert "tasks 数据暂时不可用" in briefing_run.warnings[0]
    assert isinstance(result["messages"][-1], AIMessage)


def test_handoff_command_pairs_tool_call_and_routes_to_parent() -> None:
    context = RuntimeContext(
        user_id="1",
        request_id="handoff-test",
        timezone="Asia/Shanghai",
        locale="zh-CN",
        current_datetime=datetime(2026, 7, 19, 1, 0, tzinfo=UTC),
        trigger_type="user_message",
        conversation_id=str(uuid4()),
    )
    ai_message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "transfer_to_briefing",
                "args": {"request": "生成简报", "target_date": "2026-07-19"},
                "id": "briefing-call-1",
                "type": "tool_call",
            }
        ],
    )
    runtime = ToolRuntime(
        state={"messages": [ai_message]},
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="briefing-call-1",
        store=None,
        tools=[],
    )
    handoff_function = cast(StructuredTool, transfer_to_briefing).func
    assert handoff_function is not None
    command = handoff_function(
        request="生成今天的简报",
        target_date=date(2026, 7, 19),
        runtime=runtime,
    )

    assert command.goto == "briefing_workflow"
    assert command.graph == command.PARENT
    messages = command.update["messages"]
    assert messages[0] is ai_message
    assert isinstance(messages[1], ToolMessage)
    assert messages[1].tool_call_id == "briefing-call-1"


@pytest.mark.django_db(transaction=True)
def test_outer_graph_handoff_finishes_with_tool_result_and_briefing_ai_message() -> None:
    user = User.objects.create_user(username="handoff-outer-user")
    conversation = ConversationService.create(user=user)
    operation_id = uuid4()
    envelope = TriggerEnvelope(
        trigger_type="user_message",
        user_id=str(user.pk),
        operation_id=operation_id,
        conversation_id=conversation.pk,
        payload={"message": "生成今天的简报"},
        triggered_at=datetime(2026, 7, 19, 1, 0, tzinfo=UTC),
    )
    context = runtime_context_from_trigger(
        envelope,
        request_id="handoff-outer-test",
        timezone="Asia/Shanghai",
        locale="zh-CN",
        actor=user,
    )

    def briefing_node(state: AppState, runtime: Any) -> dict[str, Any]:
        return briefing_workflow_node(
            state,
            runtime,
            editor=RunnableLambda(_editor),
        )

    graph = build_outer_graph(
        OuterGraphNodes(
            time_steward_agent=build_time_steward_agent(model=HandoffChatModel()),
            briefing_workflow=briefing_node,
            calendar_sync_workflow=lambda state: {"workflow_result": {}},
        )
    )
    result = graph.invoke(
        {
            "messages": [HumanMessage(content="生成今天的简报")],
            "trigger_type": "user_message",
            "trigger_payload": {"message": "生成今天的简报"},
            "operation_id": str(operation_id),
        },
        context=context,
    )

    tool_message = next(
        message for message in result["messages"] if isinstance(message, ToolMessage)
    )
    assert "简报生成完成" in str(tool_message.content)
    assert isinstance(result["messages"][-1], AIMessage)
    assert result["active_workflow"] == "time_steward_agent"
    assert BriefingRun.objects.get(operation_id=operation_id).status == "completed"


@pytest.mark.django_db
def test_manual_launch_api_creates_separate_briefing_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User.objects.create_user(username="briefing-api-user")
    definition = BriefingDefinitionService.default_for_user(user)
    queued: list[tuple[list[str], str]] = []

    def apply_async(*, args: list[str], task_id: str) -> None:
        queued.append((args, task_id))

    monkeypatch.setattr("apps.briefings.views.execute_agent_run_task.apply_async", apply_async)
    client = APIClient()
    client.force_authenticate(user=user)
    operation_id = uuid4()
    payload = {
        "definition_id": str(definition.pk),
        "target_date": "2026-07-19",
        "operation_id": str(operation_id),
    }
    response = client.post(
        "/api/v1/briefings/runs/",
        payload,
        format="json",
    )
    retry = client.post("/api/v1/briefings/runs/", payload, format="json")

    assert response.status_code == 202
    assert retry.status_code == 202
    assert retry.data["conversation"]["id"] == response.data["conversation"]["id"]
    assert response.data["conversation"]["kind"] == "manual_briefing"
    assert response.data["agent_run"]["trigger_type"] == "manual_briefing"
    assert response.data["agent_run"]["synthetic_input"] is True
    assert len(queued) == 1
    assert Conversation.objects.filter(user=user, kind="manual_briefing").count() == 1
