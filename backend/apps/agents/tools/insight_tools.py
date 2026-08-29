from datetime import datetime
from uuid import UUID

from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import require_actor, require_writable
from apps.insights.models import TemporalInsight
from apps.insights.services import TemporalInsightService


def _serialize(insight: TemporalInsight) -> dict[str, object]:
    return {
        "insight_id": str(insight.pk),
        "kind": insight.kind,
        "severity": insight.severity,
        "status": insight.status,
        "title": insight.title,
        "summary": insight.summary,
        "evidence": insight.evidence,
        "detected_at": insight.detected_at.isoformat(),
        "expires_at": insight.expires_at.isoformat(),
        "attention_reason": insight.attention_reason,
    }


@tool
def list_temporal_insights(
    runtime: ToolRuntime[RuntimeContext],
) -> list[dict[str, object]]:
    """List current, evidence-backed time risks after a deterministic scan."""

    actor = require_actor(runtime)
    TemporalInsightService.scan(user=actor, now=runtime.context.current_datetime)
    return [
        _serialize(insight)
        for insight in TemporalInsightService.list_open(
            user=actor,
            now=runtime.context.current_datetime,
        )
    ]


@tool
def get_temporal_insight(
    insight_id: UUID,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Read one owned time insight, including its current status and factual evidence."""

    return _serialize(
        TemporalInsightService.get(user=require_actor(runtime), insight_id=insight_id)
    )


@tool
def act_on_temporal_insight(
    insight_id: UUID,
    action: str,
    runtime: ToolRuntime[RuntimeContext],
    until: datetime | None = None,
    disable_kind: bool = False,
) -> dict[str, object]:
    """Snooze, dismiss, action or correct one owned time insight."""

    insight = TemporalInsightService.act(
        user=require_writable(runtime),
        insight_id=insight_id,
        action=action,
        until=until,
        disable_kind=disable_kind,
    )
    return _serialize(insight)


INSIGHT_READ_TOOLS = [list_temporal_insights, get_temporal_insight]
INSIGHT_WRITE_TOOLS = [act_on_temporal_insight]
INSIGHT_TOOLS = [*INSIGHT_READ_TOOLS, *INSIGHT_WRITE_TOOLS]
