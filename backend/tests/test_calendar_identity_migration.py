from datetime import UTC, datetime

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)


def test_external_event_identity_is_backfilled_from_unique_connection() -> None:
    executor = MigrationExecutor(connection)
    old_targets = [("events", "0003_event_series"), ("integrations", "0001_initial")]
    new_targets = [
        ("events", "0004_external_calendar_identity"),
        ("integrations", "0002_oauth_credentials_and_state"),
    ]
    executor.migrate(old_targets)
    old_apps = executor.loader.project_state(old_targets).apps
    User = old_apps.get_model("auth", "User")
    CalendarEvent = old_apps.get_model("events", "CalendarEvent")
    CalendarSyncConnection = old_apps.get_model("integrations", "CalendarSyncConnection")
    user = User.objects.create(username="migration-calendar-user")
    CalendarSyncConnection.objects.create(
        user_id=user.id,
        provider_name="ics",
        account_reference="https://calendar.example/private.ics",
        calendar_id="https://calendar.example/private.ics",
        calendar_name="Imported",
        timezone="Asia/Shanghai",
    )
    event = CalendarEvent.objects.create(
        user_id=user.id,
        created_by_id=user.id,
        title="Existing imported event",
        start_at=datetime(2026, 8, 24, 1, 0, tzinfo=UTC),
        end_at=datetime(2026, 8, 24, 2, 0, tzinfo=UTC),
        timezone="Asia/Shanghai",
        source="ics",
        external_id="existing-event",
    )

    executor = MigrationExecutor(connection)
    executor.migrate(new_targets)
    new_apps = executor.loader.project_state(new_targets).apps
    MigratedEvent = new_apps.get_model("events", "CalendarEvent")
    migrated = MigratedEvent.objects.get(pk=event.pk)

    assert migrated.external_account_reference == "https://calendar.example/private.ics"
    assert migrated.external_calendar_id == "https://calendar.example/private.ics"
