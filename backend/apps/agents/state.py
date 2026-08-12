import operator
from typing import Annotated, Literal, NotRequired

from langchain.agents import AgentState
from langgraph.managed import RemainingSteps
from pydantic import JsonValue

from apps.agents.triggers import TriggerType

type WorkflowName = Literal[
    "time_steward_agent",
    "briefing_workflow",
    "reminder_dispatcher",
    "calendar_sync_workflow",
]


class AppState(AgentState[None]):
    """Minimal checkpointed state shared by the outer graph and future agents."""

    trigger_type: NotRequired[TriggerType]
    trigger_payload: NotRequired[dict[str, JsonValue]]
    operation_id: NotRequired[str]
    active_workflow: NotRequired[WorkflowName]
    workflow_result: NotRequired[dict[str, JsonValue]]
    remaining_steps: NotRequired[RemainingSteps]


class TimeStewardState(AgentState[None]):
    """Agent-loop state; managed outer-graph channels intentionally stay outside it."""

    time_memory_profile: NotRequired[dict[str, JsonValue] | None]
    schedule_changed: NotRequired[Annotated[bool, operator.or_]]
