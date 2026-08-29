from datetime import datetime
from typing import Literal
from uuid import UUID

from langchain.tools import ToolRuntime, tool
from langgraph.store.base import BaseStore

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import require_actor, require_writable, tool_idempotency_key
from apps.time_memory.capacity import CapacityForecastService
from apps.time_memory.decision_profile import (
    DURATION_CATEGORY,
    DecisionProfileService,
    RecordDecisionFeedbackCommand,
)


def _require_store(runtime: ToolRuntime[RuntimeContext]) -> BaseStore:
    if runtime.store is None:
        raise ValueError("Time memory is unavailable for this run")
    return runtime.store


@tool
def recommend_task_duration(
    task_id: UUID,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Get an explainable duration recommendation for one owned task."""

    recommendation = DecisionProfileService.recommend_duration(
        user=require_actor(runtime),
        store=_require_store(runtime),
        task_id=task_id,
        now=runtime.context.current_datetime,
    )
    return recommendation.as_dict()


@tool
def get_capacity_forecast(
    range_start: datetime,
    range_end: datetime,
    runtime: ToolRuntime[RuntimeContext],
    slot_minutes: int = 30,
) -> dict[str, object]:
    """Get deterministic capacity risk and its reason codes for a time range."""

    forecast = CapacityForecastService.forecast(
        user=require_actor(runtime),
        range_start=range_start,
        range_end=range_end,
        slot_minutes=slot_minutes,
    )
    return {
        "range_start": forecast.range_start.isoformat(),
        "range_end": forecast.range_end.isoformat(),
        "available_minutes": forecast.available_minutes,
        "committed_minutes": forecast.committed_minutes,
        "unplanned_minutes": forecast.unplanned_minutes,
        "risk": forecast.risk,
        "reason_codes": list(forecast.reason_codes),
    }


@tool
def record_task_duration_feedback(
    task_id: UUID,
    action: Literal["accept", "too_short", "too_long"],
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Record explicit feedback on a task duration recommendation."""

    actor = require_writable(runtime)
    recommendation = DecisionProfileService.recommend_duration(
        user=actor,
        store=_require_store(runtime),
        task_id=task_id,
        now=runtime.context.current_datetime,
    )
    feedback = DecisionProfileService.record_feedback(
        RecordDecisionFeedbackCommand(
            user=actor,
            category=DURATION_CATEGORY,
            action=action,
            value={
                "task_id": str(task_id),
                "segment": recommendation.segment,
                "recommended_minutes": recommendation.recommended_minutes,
            },
            idempotency_key=tool_idempotency_key(runtime, purpose="duration-feedback"),
            source="agent",
        )
    )
    return {
        "feedback_id": str(feedback.pk),
        "task_id": str(task_id),
        "action": feedback.action,
        "segment": recommendation.segment,
    }


DECISION_READ_TOOLS = [recommend_task_duration, get_capacity_forecast]
DECISION_WRITE_TOOLS = [record_task_duration_feedback]
DECISION_TOOLS = [*DECISION_READ_TOOLS, *DECISION_WRITE_TOOLS]
