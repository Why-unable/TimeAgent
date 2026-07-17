from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
from langgraph.types import Command, Interrupt
from pydantic import JsonValue

from apps.agents.context import RuntimeContext
from apps.agents.execution import (
    GraphExecutionLimits,
    GraphStepLimitExceededError,
    get_graph_execution_limits,
)
from apps.agents.routing import (
    ensure_context_matches_trigger,
    graph_config_for_thread,
    graph_config_from_trigger,
    required_payload_uuid,
    route_trigger,
    state_from_trigger,
)
from apps.agents.state import AppState
from apps.agents.triggers import TriggerEnvelope
from apps.reminders.dispatcher import ReminderDispatcher

type OuterGraphNode = Runnable[AppState, Any] | Callable[[AppState], Any]
type CompiledOuterGraph = CompiledStateGraph[
    AppState,
    RuntimeContext,
    AppState,
    AppState,
]


class RuntimeContextMismatchError(ValueError):
    pass


class NoPendingInterruptError(RuntimeError):
    pass


class StatelessTriggerResumeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OuterGraphNodes:
    time_steward_agent: OuterGraphNode
    briefing_workflow: OuterGraphNode
    calendar_sync_workflow: OuterGraphNode


@dataclass(frozen=True, slots=True)
class OuterGraphRuntime:
    """Select the persistent or stateless compiled graph for a trigger."""

    persistent_graph: CompiledOuterGraph
    stateless_graph: CompiledOuterGraph
    limits: GraphExecutionLimits

    def invoke(
        self,
        envelope: TriggerEnvelope,
        context: RuntimeContext,
    ) -> AppState:
        ensure_context_matches_trigger(envelope, context)
        graph = (
            self.stateless_graph
            if envelope.trigger_type == "reminder_due"
            else self.persistent_graph
        )
        return self._invoke(
            graph,
            state_from_trigger(envelope),
            config=graph_config_from_trigger(envelope, context, limits=self.limits),
            context=context,
        )

    async def ainvoke(
        self,
        envelope: TriggerEnvelope,
        context: RuntimeContext,
    ) -> AppState:
        ensure_context_matches_trigger(envelope, context)
        graph = (
            self.stateless_graph
            if envelope.trigger_type == "reminder_due"
            else self.persistent_graph
        )
        return await self._ainvoke(
            graph,
            state_from_trigger(envelope),
            config=graph_config_from_trigger(envelope, context, limits=self.limits),
            context=context,
        )

    def pending_interrupts(self, thread_id: str) -> tuple[Interrupt, ...]:
        config = graph_config_for_thread(thread_id, request_id="state-inspection")
        return self.persistent_graph.get_state(config).interrupts

    async def apending_interrupts(self, thread_id: str) -> tuple[Interrupt, ...]:
        config = graph_config_for_thread(thread_id, request_id="state-inspection")
        snapshot = await self.persistent_graph.aget_state(config)
        return snapshot.interrupts

    def resume(
        self,
        *,
        thread_id: str,
        resume_value: JsonValue,
        context: RuntimeContext,
    ) -> AppState:
        self._validate_resume(thread_id, context)
        if not self.pending_interrupts(thread_id):
            raise NoPendingInterruptError(f"Thread {thread_id} has no pending interrupt")
        config = graph_config_for_thread(
            thread_id,
            request_id=context.request_id,
            user_id=context.user_id,
            trigger_type=context.trigger_type,
            limits=self.limits,
        )
        return self._invoke(
            self.persistent_graph,
            Command(resume=resume_value),
            config=config,
            context=context,
        )

    async def aresume(
        self,
        *,
        thread_id: str,
        resume_value: JsonValue,
        context: RuntimeContext,
    ) -> AppState:
        self._validate_resume(thread_id, context)
        if not await self.apending_interrupts(thread_id):
            raise NoPendingInterruptError(f"Thread {thread_id} has no pending interrupt")
        config = graph_config_for_thread(
            thread_id,
            request_id=context.request_id,
            user_id=context.user_id,
            trigger_type=context.trigger_type,
            limits=self.limits,
        )
        return await self._ainvoke(
            self.persistent_graph,
            Command(resume=resume_value),
            config=config,
            context=context,
        )

    def _validate_resume(self, thread_id: str, context: RuntimeContext) -> None:
        if context.trigger_type == "reminder_due":
            raise StatelessTriggerResumeError("reminder_due runs cannot be resumed")
        if context.conversation_id is not None and context.conversation_id != thread_id.strip():
            raise RuntimeContextMismatchError(
                "RuntimeContext.conversation_id must match the resumed thread_id"
            )

    def _invoke(
        self,
        graph: CompiledOuterGraph,
        graph_input: AppState | Command[Any],
        *,
        config: RunnableConfig,
        context: RuntimeContext,
    ) -> AppState:
        try:
            return cast(
                AppState,
                graph.invoke(graph_input, config=config, context=context),
            )
        except GraphRecursionError as exc:
            raise GraphStepLimitExceededError(self.limits.recursion_limit) from exc

    async def _ainvoke(
        self,
        graph: CompiledOuterGraph,
        graph_input: AppState | Command[Any],
        *,
        config: RunnableConfig,
        context: RuntimeContext,
    ) -> AppState:
        try:
            return cast(
                AppState,
                await graph.ainvoke(graph_input, config=config, context=context),
            )
        except GraphRecursionError as exc:
            raise GraphStepLimitExceededError(self.limits.recursion_limit) from exc


def validate_runtime_context(
    state: AppState,
    runtime: Runtime[RuntimeContext],
) -> dict[str, object]:
    context = runtime.context
    state_trigger_type = state.get("trigger_type")
    if state_trigger_type is None:
        raise RuntimeContextMismatchError("AppState.trigger_type is required")
    if state_trigger_type != context.trigger_type:
        raise RuntimeContextMismatchError("State and RuntimeContext disagree on trigger_type")
    if not state.get("operation_id", "").strip():
        raise RuntimeContextMismatchError("AppState.operation_id is required")
    return {}


def reminder_dispatcher_node(
    state: AppState,
    runtime: Runtime[RuntimeContext],
) -> dict[str, dict[str, JsonValue]]:
    payload = state.get("trigger_payload", {})
    reminder_id = required_payload_uuid(payload, "reminder_id")
    delivered = ReminderDispatcher.send_reminder(
        reminder_id,
        now=runtime.context.current_datetime,
    )
    return {
        "workflow_result": {
            "workflow": "reminder_dispatcher",
            "reminder_id": str(reminder_id),
            "delivered": delivered,
        }
    }


def build_outer_graph(
    nodes: OuterGraphNodes,
    *,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    store: BaseStore | None = None,
) -> CompiledOuterGraph:
    builder = StateGraph(AppState, context_schema=RuntimeContext)
    builder.add_node("validate_runtime_context", validate_runtime_context)
    builder.add_node(
        "route_by_trigger",
        route_trigger,
        destinations=(
            "time_steward_agent",
            "briefing_workflow",
            "reminder_dispatcher",
            "calendar_sync_workflow",
        ),
    )
    builder.add_node("time_steward_agent", _as_runnable(nodes.time_steward_agent))
    builder.add_node("briefing_workflow", _as_runnable(nodes.briefing_workflow))
    builder.add_node("reminder_dispatcher", reminder_dispatcher_node)
    builder.add_node(
        "calendar_sync_workflow",
        _as_runnable(nodes.calendar_sync_workflow),
    )

    builder.add_edge(START, "validate_runtime_context")
    builder.add_edge("validate_runtime_context", "route_by_trigger")
    for destination in (
        "time_steward_agent",
        "briefing_workflow",
        "reminder_dispatcher",
        "calendar_sync_workflow",
    ):
        builder.add_edge(destination, END)

    return builder.compile(
        checkpointer=checkpointer,
        store=store,
        name="time_agent_outer_graph",
    )


def build_outer_graph_runtime(
    nodes: OuterGraphNodes,
    *,
    checkpointer: BaseCheckpointSaver[str],
    store: BaseStore,
    limits: GraphExecutionLimits | None = None,
) -> OuterGraphRuntime:
    resolved_limits = limits or get_graph_execution_limits()
    return OuterGraphRuntime(
        persistent_graph=build_outer_graph(
            nodes,
            checkpointer=checkpointer,
            store=store,
        ),
        stateless_graph=build_outer_graph(nodes),
        limits=resolved_limits,
    )


def _as_runnable(node: OuterGraphNode) -> Runnable[AppState, Any]:
    if isinstance(node, Runnable):
        return node
    return RunnableLambda(node)
