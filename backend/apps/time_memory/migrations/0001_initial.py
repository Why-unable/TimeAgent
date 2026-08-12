import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="TimeMemoryRefreshState",
            fields=[
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="time_memory_refresh_state",
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("clean", "Clean"),
                            ("dirty", "Dirty"),
                            ("processing", "Processing"),
                            ("failed", "Failed"),
                        ],
                        default="dirty",
                        max_length=16,
                    ),
                ),
                ("dirty_at", models.DateTimeField(blank=True, null=True)),
                ("last_started_at", models.DateTimeField(blank=True, null=True)),
                ("last_completed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ScheduleChange",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "entity_type",
                    models.CharField(
                        choices=[("event", "Event"), ("task", "Task")],
                        max_length=16,
                    ),
                ),
                ("entity_id", models.UUIDField()),
                (
                    "operation",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("updated", "Updated"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("agent", "Agent"),
                            ("web", "Web"),
                            ("android", "Android"),
                            ("external_calendar", "External calendar"),
                            ("system", "System"),
                        ],
                        max_length=32,
                    ),
                ),
                ("old_snapshot", models.JSONField(blank=True, default=dict)),
                ("new_snapshot", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="time_memory_schedule_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["occurred_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="schedulechange",
            index=models.Index(
                fields=["user", "occurred_at"],
                name="time_memory_user_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="schedulechange",
            index=models.Index(
                fields=["user", "entity_type", "entity_id"],
                name="time_memory_entity_idx",
            ),
        ),
    ]
