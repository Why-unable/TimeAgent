from dataclasses import dataclass
from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.db import transaction

from apps.events.models import CalendarEventStatus, EventSeries, EventSeriesStatus
from apps.events.services import CreateEventCommand, EventService
from apps.tasks.models import Task


@dataclass(frozen=True, slots=True)
class CreateEventSeriesCommand:
    user: User
    title: str
    start_at: datetime
    end_at: datetime
    timezone: str
    frequency: str
    occurrence_count: int
    task: Task | None = None
    description: str = ""
    location: str = ""
    interval: int = 1


class EventSeriesService:
    @staticmethod
    def preview_occurrence_windows(
        *,
        start_at: datetime,
        end_at: datetime,
        frequency: str,
        interval: int,
        occurrence_count: int,
    ) -> list[tuple[datetime, datetime]]:
        """Build finite recurrence windows without writing any business data."""

        if occurrence_count < 1:
            raise ValueError("occurrence_count must be at least one")
        if interval < 1:
            raise ValueError("interval must be at least one")
        if end_at <= start_at:
            raise ValueError("end_at must be later than start_at")

        duration = end_at - start_at
        occurrence_start = start_at
        windows: list[tuple[datetime, datetime]] = []
        for _ in range(occurrence_count):
            windows.append((occurrence_start, occurrence_start + duration))
            occurrence_start = EventSeriesService._next_start(
                occurrence_start,
                frequency,
                interval,
            )
        return windows

    @staticmethod
    @transaction.atomic
    def create_series(command: CreateEventSeriesCommand) -> EventSeries:
        series = EventSeries(
            user=command.user,
            task=command.task,
            title=command.title,
            description=command.description,
            start_at=command.start_at,
            end_at=command.end_at,
            timezone=command.timezone,
            location=command.location,
            frequency=command.frequency,
            interval=command.interval,
            occurrence_count=command.occurrence_count,
        )
        series.full_clean()
        series.save()
        for start_at, end_at in EventSeriesService.preview_occurrence_windows(
            start_at=command.start_at,
            end_at=command.end_at,
            frequency=command.frequency,
            interval=command.interval,
            occurrence_count=command.occurrence_count,
        ):
            EventService.create_event(
                CreateEventCommand(
                    user=command.user,
                    task=command.task,
                    series=series,
                    title=command.title,
                    description=command.description,
                    start_at=start_at,
                    end_at=end_at,
                    timezone=command.timezone,
                    location=command.location,
                    status=CalendarEventStatus.CONFIRMED,
                )
            )
        return series

    @staticmethod
    @transaction.atomic
    def cancel_series(*, series: EventSeries, user: User) -> EventSeries:
        locked = EventSeries.objects.select_for_update().get(pk=series.pk, user=user)
        if locked.status == EventSeriesStatus.CANCELLED:
            return locked
        locked.status = EventSeriesStatus.CANCELLED
        locked.version += 1
        locked.save(update_fields=["status", "version", "updated_at"])
        for event in locked.occurrences.exclude(status=CalendarEventStatus.CANCELLED):
            EventService.cancel_event(event_id=event.pk, user=user, expected_version=event.version)
        return locked

    @staticmethod
    def _next_start(start_at: datetime, frequency: str, interval: int) -> datetime:
        if frequency == "daily":
            return start_at + timedelta(days=interval)
        if frequency == "weekly":
            return start_at + timedelta(days=7 * interval)
        if frequency == "monthly":
            month = start_at.month - 1 + interval
            year = start_at.year + month // 12
            return start_at.replace(year=year, month=month % 12 + 1)
        raise ValueError("Unsupported recurrence frequency")
