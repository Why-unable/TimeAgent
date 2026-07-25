import uuid

import django.db.models.deletion
from django.core.validators import MinValueValidator
from django.db import migrations, models
from django.db.models import Q

import apps.preferences.models


class Migration(migrations.Migration):
    dependencies = [("events", "0002_task_links_and_scheduling")]

    operations = [
        migrations.CreateModel(
            name="EventSeries",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("start_at", models.DateTimeField()),
                ("end_at", models.DateTimeField()),
                (
                    "timezone",
                    models.CharField(
                        max_length=64,
                        validators=[apps.preferences.models.validate_iana_timezone],
                    ),
                ),
                ("location", models.CharField(blank=True, max_length=255)),
                (
                    "visibility",
                    models.CharField(
                        choices=[("private", "Private"), ("public", "Public")],
                        default="private",
                        max_length=16,
                    ),
                ),
                ("frequency", models.CharField(max_length=16)),
                (
                    "interval",
                    models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)]),
                ),
                ("weekdays", models.JSONField(blank=True, default=list)),
                ("month_days", models.JSONField(blank=True, default=list)),
                ("ends_on", models.DateField(blank=True, null=True)),
                ("occurrence_count", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("cancelled", "Cancelled")],
                        default="active",
                        max_length=16,
                    ),
                ),
                (
                    "version",
                    models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)]),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="tasks.task",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="auth.user"),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="eventseries",
            constraint=models.CheckConstraint(
                condition=Q(("end_at__gt", models.F("start_at"))),
                name="event_series_end_after_start",
            ),
        ),
        migrations.AddConstraint(
            model_name="eventseries",
            constraint=models.CheckConstraint(
                condition=Q(("version__gte", 1)), name="event_series_version_positive"
            ),
        ),
        migrations.AddField(
            model_name="calendarevent",
            name="series",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="occurrences",
                to="events.eventseries",
            ),
        ),
    ]
