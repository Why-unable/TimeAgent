from django.db import migrations, models


def backfill_external_identity(apps, schema_editor) -> None:
    del schema_editor
    CalendarEvent = apps.get_model("events", "CalendarEvent")
    CalendarSyncConnection = apps.get_model("integrations", "CalendarSyncConnection")
    for event in CalendarEvent.objects.exclude(source="local").iterator():
        connections = list(
            CalendarSyncConnection.objects.filter(
                user_id=event.user_id,
                provider_name=event.source,
            ).values_list("account_reference", "calendar_id")[:2]
        )
        if len(connections) == 1:
            account_reference, calendar_id = connections[0]
        else:
            account_reference = f"legacy:{event.source}"[:255]
            calendar_id = f"legacy:{event.source}"[:255]
        event.external_account_reference = account_reference
        event.external_calendar_id = calendar_id
        event.save(update_fields=["external_account_reference", "external_calendar_id"])


def clear_external_identity(apps, schema_editor) -> None:
    del schema_editor
    CalendarEvent = apps.get_model("events", "CalendarEvent")
    CalendarEvent.objects.update(external_account_reference="", external_calendar_id="")


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0003_event_series"),
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendarevent",
            name="external_account_reference",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="calendarevent",
            name="external_calendar_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.RunPython(backfill_external_identity, clear_external_identity),
        migrations.RemoveConstraint(
            model_name="calendarevent",
            name="calendar_event_external_identity_consistent",
        ),
        migrations.RemoveConstraint(
            model_name="calendarevent",
            name="calendar_event_unique_external_identity",
        ),
        migrations.AddConstraint(
            model_name="calendarevent",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        source="local",
                        external_id="",
                        external_account_reference="",
                        external_calendar_id="",
                    )
                    | (
                        ~models.Q(source="local")
                        & ~models.Q(external_id="")
                        & ~models.Q(external_account_reference="")
                        & ~models.Q(external_calendar_id="")
                    )
                ),
                name="calendar_event_external_identity_consistent",
            ),
        ),
        migrations.AddConstraint(
            model_name="calendarevent",
            constraint=models.UniqueConstraint(
                condition=~models.Q(external_id=""),
                fields=(
                    "user",
                    "source",
                    "external_account_reference",
                    "external_calendar_id",
                    "external_id",
                ),
                name="calendar_event_unique_external_identity",
            ),
        ),
    ]
