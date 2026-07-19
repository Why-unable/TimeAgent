from datetime import datetime, timedelta
from typing import Any

from django.contrib.auth.models import User

from apps.briefings.registry import BriefingRegistry, SectionContext
from apps.briefings.schemas import SectionResult, SourceReference
from apps.events.models import CalendarEventStatus
from apps.events.services import EventQuery, EventService
from apps.external_data.configuration import get_provider_config
from apps.external_data.providers import NewsProvider, WeatherProvider
from apps.external_data.services import (
    NewsDataService,
    WeatherDataService,
    WeatherLocationNotConfiguredError,
)
from apps.tasks.models import TaskStatus
from apps.tasks.services import TaskQuery, TaskService
from common.time import to_user_timezone


def _local_iso(value: datetime | None, timezone: str) -> str | None:
    return to_user_timezone(value, timezone).isoformat() if value is not None else None


def _required_local_iso(value: datetime, timezone: str) -> str:
    return to_user_timezone(value, timezone).isoformat()


class CalendarBriefingSection:
    key = "calendar"

    def collect(self, *, user: User, context: SectionContext) -> SectionResult:
        event_records = EventService.list_events(
            EventQuery(
                user=user,
                starts_before=context.day_end_at,
                ends_after=context.day_start_at,
                statuses=(CalendarEventStatus.CONFIRMED, CalendarEventStatus.TENTATIVE),
            )
        )
        event_records.sort(key=lambda item: (item.start_at, item.end_at, str(item.pk)))
        events_data: list[dict[str, Any]] = [
            {
                "id": str(event.pk),
                "title": event.title,
                "start_at": _local_iso(event.start_at, context.timezone),
                "end_at": _local_iso(event.end_at, context.timezone),
                "location": event.location,
                "status": event.status,
            }
            for event in event_records
        ]
        conflicts: list[dict[str, str]] = []
        for index, event in enumerate(event_records):
            for other in event_records[index + 1 :]:
                if other.start_at >= event.end_at:
                    break
                conflicts.append(
                    {
                        "first_id": str(event.pk),
                        "second_id": str(other.pk),
                        "overlap_start_at": _required_local_iso(
                            max(event.start_at, other.start_at), context.timezone
                        ),
                        "overlap_end_at": _required_local_iso(
                            min(event.end_at, other.end_at), context.timezone
                        ),
                    }
                )
        sources = [
            SourceReference(
                kind="calendar_event",
                id=str(event.pk),
                title=event.title,
                occurred_at=event.start_at,
            )
            for event in event_records
        ]
        next_event = next(
            (event for event in event_records if event.start_at >= context.current_datetime), None
        )
        minutes_until = (
            max(0, int((next_event.start_at - context.current_datetime).total_seconds() // 60))
            if next_event
            else None
        )
        return SectionResult(
            key=self.key,
            status="completed",
            data={
                "events": events_data,
                "conflicts": conflicts,
                "next_event_id": str(next_event.pk) if next_event else None,
                "minutes_until_next_event": minutes_until,
                "day_start_at": _local_iso(context.day_start_at, context.timezone),
                "day_end_at": _local_iso(context.day_end_at, context.timezone),
            },
            sources=sources,
        )


class TaskBriefingSection:
    key = "tasks"

    def collect(self, *, user: User, context: SectionContext) -> SectionResult:
        active_statuses = (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
        planned = TaskService.list_tasks(
            TaskQuery(
                user=user,
                statuses=active_statuses,
                planned_starts_before=context.day_end_at,
                planned_ends_after=context.day_start_at,
            )
        )
        due_or_overdue = TaskService.list_tasks(
            TaskQuery(user=user, statuses=active_statuses, due_before=context.day_end_at)
        )
        due = [
            task for task in due_or_overdue if task.due_at and task.due_at >= context.day_start_at
        ]
        overdue = [
            task for task in due_or_overdue if task.due_at and task.due_at < context.day_start_at
        ]
        planned.sort(key=lambda item: (item.planned_start_at, str(item.pk)))
        due.sort(key=lambda item: (item.due_at, str(item.pk)))
        overdue.sort(key=lambda item: (item.due_at, str(item.pk)))
        groups = {
            "planned": planned,
            "due": due,
            "overdue": overdue,
        }
        data: dict[str, Any] = {}
        unique_sources: dict[str, SourceReference] = {}
        for group, tasks in groups.items():
            data[group] = [
                {
                    "id": str(task.pk),
                    "title": task.title,
                    "status": task.status,
                    "priority": task.priority,
                    "planned_start_at": _local_iso(task.planned_start_at, context.timezone),
                    "planned_end_at": _local_iso(task.planned_end_at, context.timezone),
                    "due_at": _local_iso(task.due_at, context.timezone),
                }
                for task in tasks
            ]
            for task in tasks:
                unique_sources[str(task.pk)] = SourceReference(
                    kind="task",
                    id=str(task.pk),
                    title=task.title,
                    occurred_at=task.due_at or task.planned_start_at,
                )
        return SectionResult(
            key=self.key,
            status="completed",
            data=data,
            sources=list(unique_sources.values()),
        )


class WeatherBriefingSection:
    key = "weather"

    def __init__(self, provider: WeatherProvider | None = None) -> None:
        self.provider = provider

    def collect(self, *, user: User, context: SectionContext) -> SectionResult:
        try:
            forecast = WeatherDataService.forecast_for_user(
                user=user,
                start_date=context.target_date,
                requested_at=context.current_datetime,
                locale=context.locale,
                provider=self.provider,
            )
        except WeatherLocationNotConfiguredError as exc:
            return SectionResult(
                key=self.key,
                status="completed",
                warnings=[str(exc)],
            )
        location_label = ", ".join(
            item
            for item in [
                forecast.location.name,
                forecast.location.admin1,
                forecast.location.country,
            ]
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
                    occurred_at=context.day_start_at,
                    url=str(forecast.source_url),
                    publisher=forecast.provider,
                )
            )
        return SectionResult(
            key=self.key,
            status="completed",
            data={
                "provider": forecast.provider,
                "location": forecast.location.model_dump(mode="json"),
                "daily": daily,
                "units": forecast.units,
                "generated_at": forecast.generated_at.isoformat(),
            },
            sources=sources,
        )


class NewsBriefingSection:
    key = "news"

    def __init__(self, provider: NewsProvider | None = None) -> None:
        self.provider = provider

    def collect(self, *, user: User, context: SectionContext) -> SectionResult:
        config = get_provider_config().news
        effective_end = min(context.current_datetime, context.day_end_at)
        effective_start = effective_end - timedelta(hours=config.lookback_hours)
        collection = NewsDataService.collect_for_user(
            user=user,
            start_at=effective_start,
            end_at=effective_end,
            provider=self.provider,
        )
        if collection.selected_feeds and not collection.successful_feeds:
            return SectionResult(
                key=self.key,
                status="failed",
                warnings=collection.warnings or ["新闻 Provider 暂时不可用。"],
                error_code="NewsProvidersUnavailable",
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
        return SectionResult(
            key=self.key,
            status="completed",
            data={
                "items": items,
                "window_start": effective_start.isoformat(),
                "window_end": effective_end.isoformat(),
                "selected_feeds": collection.selected_feeds,
            },
            sources=sources,
            warnings=collection.warnings,
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


DEFAULT_BRIEFING_REGISTRY = BriefingRegistry.from_sections(
    [
        CalendarBriefingSection(),
        TaskBriefingSection(),
        WeatherBriefingSection(),
        NewsBriefingSection(),
    ]
)
