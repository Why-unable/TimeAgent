from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import model_dict, require_actor
from apps.briefings.schemas import ResearchToolResult, SourceReference
from apps.briefings.state import BriefingAgentState
from apps.events.models import CalendarEventStatus
from apps.events.services import EventQuery, EventService
from apps.external_data.configuration import get_provider_config
from apps.external_data.services import NewsDataService, WeatherDataService
from apps.preferences.services import UserPreferenceService
from apps.tasks.models import TaskStatus
from apps.tasks.services import TaskQuery, TaskService
from common.time import get_timezone, to_utc


def _date_window(
    start_date: date,
    end_date: date,
    timezone_name: str,
) -> tuple[datetime, datetime]:
    if end_date < start_date:
        raise ValueError("end_date must not be earlier than start_date")
    if (end_date - start_date).days > 366:
        raise ValueError("research date range cannot exceed 367 days")
    zone = get_timezone(timezone_name)
    start_at = datetime.combine(start_date, time.min, tzinfo=zone).astimezone(UTC)
    end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start_at, end_at


def _command(
    runtime: ToolRuntime[RuntimeContext, BriefingAgentState],
    result: ResearchToolResult,
) -> Command[Any]:
    tool_call_id = (runtime.tool_call_id or "").strip()
    if not tool_call_id:
        raise RuntimeError("Briefing research tools require a tool call ID")
    payload = result.model_dump(mode="json")
    runtime.stream_writer(
        {
            "event_type": "briefing.research.completed",
            "payload": {
                "tool": result.tool_name,
                "section": result.section,
                "status": result.status,
            },
        }
    )
    return Command(
        update={
            "research_results": [result],
            "messages": [
                ToolMessage(
                    content=json.dumps(payload, ensure_ascii=False),
                    artifact=payload,
                    tool_call_id=tool_call_id,
                    name=result.tool_name,
                )
            ],
        }
    )


@tool
def research_calendar(
    start_date: date,
    end_date: date,
    runtime: ToolRuntime[RuntimeContext, BriefingAgentState],
) -> Command[Any]:
    """Read calendar events in an inclusive local-date range. Never modifies events."""

    actor = require_actor(runtime)
    start_at, end_at = _date_window(start_date, end_date, runtime.context.timezone)
    events = EventService.list_events(
        EventQuery(
            user=actor,
            starts_before=end_at,
            ends_after=start_at,
            statuses=(CalendarEventStatus.TENTATIVE, CalendarEventStatus.CONFIRMED),
        )
    )
    fields = (
        "id",
        "title",
        "description",
        "start_at",
        "end_at",
        "timezone",
        "location",
        "status",
    )
    sources = [
        SourceReference(
            kind="calendar_event",
            id=str(item.pk),
            title=item.title,
            occurred_at=item.start_at,
        )
        for item in events
    ]
    return _command(
        runtime,
        ResearchToolResult(
            tool_name="research_calendar",
            section="calendar",
            status="completed" if events else "no_results",
            range_start=start_at.isoformat(),
            range_end=end_at.isoformat(),
            data={"events": [model_dict(item, fields) for item in events]},
            sources=sources,
        ),
    )


@tool
def research_tasks(
    start_date: date,
    end_date: date,
    runtime: ToolRuntime[RuntimeContext, BriefingAgentState],
    include_overdue: bool = True,
) -> Command[Any]:
    """Read active tasks relevant to an inclusive local-date range. Never modifies tasks."""

    actor = require_actor(runtime)
    start_at, end_at = _date_window(start_date, end_date, runtime.context.timezone)
    statuses = (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
    planned = TaskService.list_tasks(
        TaskQuery(
            user=actor,
            statuses=statuses,
            planned_starts_before=end_at,
            planned_ends_after=start_at,
        )
    )
    due_candidates = TaskService.list_tasks(
        TaskQuery(user=actor, statuses=statuses, due_before=end_at)
    )
    due = [item for item in due_candidates if item.due_at and item.due_at >= start_at]
    overdue = [item for item in due_candidates if item.due_at and item.due_at < start_at]
    if not include_overdue:
        overdue = []
    ordered: dict[str, Any] = {}
    for item in [*overdue, *due, *planned]:
        ordered[str(item.pk)] = item
    fields = (
        "id",
        "title",
        "description",
        "project",
        "status",
        "priority",
        "due_at",
        "estimated_minutes",
        "planned_start_at",
        "planned_end_at",
        "tags",
    )
    sources = [
        SourceReference(
            kind="task",
            id=str(item.pk),
            title=item.title,
            occurred_at=item.due_at or item.planned_start_at,
        )
        for item in ordered.values()
    ]
    return _command(
        runtime,
        ResearchToolResult(
            tool_name="research_tasks",
            section="tasks",
            status="completed" if ordered else "no_results",
            range_start=start_at.isoformat(),
            range_end=end_at.isoformat(),
            data={
                "overdue": [model_dict(item, fields) for item in overdue],
                "due": [model_dict(item, fields) for item in due],
                "planned": [model_dict(item, fields) for item in planned],
            },
            sources=sources,
        ),
    )


@tool
def research_weather(
    start_date: date,
    end_date: date,
    runtime: ToolRuntime[RuntimeContext, BriefingAgentState],
    location: str = "",
) -> Command[Any]:
    """Fetch a weather forecast for a location and inclusive date range, up to provider limits."""

    actor = require_actor(runtime)
    preference = UserPreferenceService.get_for_user(actor)
    if preference is not None:
        configured_end = start_date + timedelta(days=preference.weather_forecast_days - 1)
        end_date = min(end_date, configured_end)
    forecast = WeatherDataService.forecast_for_user(
        user=actor,
        start_date=start_date,
        end_date=end_date,
        requested_at=runtime.context.current_datetime,
        locale=runtime.context.locale,
        location_query=location or None,
    )
    location_label = ", ".join(
        item
        for item in [forecast.location.name, forecast.location.admin1, forecast.location.country]
        if item
    )
    daily = []
    sources = []
    for item in forecast.daily:
        source_id = (
            f"weather:{forecast.location.latitude:.4f}:"
            f"{forecast.location.longitude:.4f}:{item.date.isoformat()}"
        )
        daily.append(
            {
                "id": source_id,
                "date": item.date.isoformat(),
                "location": location_label,
                "weather_code": item.weather_code,
                "condition": _weather_condition(item.weather_code),
                "temperature_min": item.temperature_min,
                "temperature_max": item.temperature_max,
                "precipitation_probability": item.precipitation_probability,
                "precipitation_sum": item.precipitation_sum,
                "wind_speed_max": item.wind_speed_max,
                "sunrise": item.sunrise.isoformat() if item.sunrise else None,
                "sunset": item.sunset.isoformat() if item.sunset else None,
            }
        )
        sources.append(
            SourceReference(
                kind="weather_forecast",
                id=source_id,
                title=f"{location_label} {item.date.isoformat()} 天气",
                occurred_at=runtime.context.current_datetime,
                url=str(forecast.source_url),
                publisher=forecast.provider,
            )
        )
    expected_days = (end_date - start_date).days + 1
    warnings = []
    status: Literal["completed", "partial", "no_results", "failed"] = "completed"
    if len(daily) < expected_days:
        status = "partial"
        warnings.append(f"天气 Provider 仅返回 {len(daily)}/{expected_days} 天数据。")
    return _command(
        runtime,
        ResearchToolResult(
            tool_name="research_weather",
            section="weather",
            status=status,
            range_start=start_date.isoformat(),
            range_end=end_date.isoformat(),
            data={
                "provider": forecast.provider,
                "location": forecast.location.model_dump(mode="json"),
                "daily": daily,
                "units": forecast.units,
                "generated_at": forecast.generated_at.isoformat(),
            },
            sources=sources,
            warnings=warnings,
        ),
    )


@tool
def research_news(
    topics: list[str],
    start_at: datetime,
    end_at: datetime,
    runtime: ToolRuntime[RuntimeContext, BriefingAgentState],
    limit: int = 12,
) -> Command[Any]:
    """Search trusted RSS feeds for arbitrary topics; unknown topics use catalog-wide fallback."""

    if end_at < start_at:
        raise ValueError("end_at must not be earlier than start_at")
    if end_at - start_at > timedelta(days=7):
        raise ValueError("news search range cannot exceed 7 days")
    actor = require_actor(runtime)
    collection = NewsDataService.collect_for_user(
        user=actor,
        start_at=to_utc(start_at),
        end_at=to_utc(end_at),
        topics=topics,
        limit=limit,
    )
    if collection.selected_feeds and not collection.successful_feeds:
        raise ConnectionError(
            "All selected trusted news feeds failed; retry the bounded news research call"
        )
    items = [
        {
            "id": str(item.pk),
            "title": item.title,
            "summary": item.summary,
            "publisher": item.publisher,
            "author": item.author,
            "url": item.canonical_url,
            "published_at": item.published_at.isoformat(),
            "categories": item.categories,
            "matched_topics": collection.matched_topics.get(str(item.pk), []),
        }
        for item in collection.items
    ]
    sources = [
        SourceReference(
            kind="news_article",
            id=str(item.pk),
            title=item.title,
            occurred_at=item.published_at,
            url=item.canonical_url,
            publisher=item.publisher,
        )
        for item in collection.items
    ]
    status: Literal["completed", "partial", "no_results", "failed"] = (
        "completed" if items else "no_results"
    )
    if collection.warnings and items:
        status = "partial"
    return _command(
        runtime,
        ResearchToolResult(
            tool_name="research_news",
            section="news",
            status=status,
            range_start=to_utc(start_at).isoformat(),
            range_end=to_utc(end_at).isoformat(),
            data={
                "topics": topics,
                "items": items,
                "selected_feeds": collection.selected_feeds,
                "successful_feeds": collection.successful_feeds,
            },
            sources=sources,
            warnings=collection.warnings,
            error_code="NewsProvidersUnavailable" if status == "failed" else "",
        ),
    )


@tool
def get_news_source_catalog(
    runtime: ToolRuntime[RuntimeContext, BriefingAgentState],
) -> Command[Any]:
    """Inspect the trusted RSS source catalog and topic labels before refining a news search."""

    require_actor(runtime)
    feeds = get_provider_config().news.feeds
    return _command(
        runtime,
        ResearchToolResult(
            tool_name="get_news_source_catalog",
            section="news_catalog",
            status="completed",
            data={
                "feeds": [
                    {
                        "name": feed.name,
                        "publisher": feed.publisher,
                        "topics": feed.topics,
                        "priority": feed.priority,
                    }
                    for feed in feeds
                ]
            },
        ),
    )


def _weather_condition(code: int | None) -> str:
    if code is None:
        return "未知"
    if code == 0:
        return "晴"
    if code in {1, 2, 3}:
        return "多云"
    if code in {45, 48}:
        return "雾"
    if code in {51, 53, 55, 56, 57}:
        return "毛毛雨"
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "降雨"
    if code in {71, 73, 75, 77, 85, 86}:
        return "降雪"
    if code in {95, 96, 99}:
        return "雷暴"
    return "天气变化"


BRIEFING_RESEARCH_TOOLS = [
    research_calendar,
    research_tasks,
    research_weather,
    research_news,
    get_news_source_catalog,
]

EXTERNAL_RESEARCH_TOOLS = [research_weather, research_news]
