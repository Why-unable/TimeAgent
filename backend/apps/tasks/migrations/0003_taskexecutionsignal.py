# Generated manually for the Phase A execution-evidence boundary.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tasks", "0002_task_version"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskExecutionSignal",
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
                    "signal_type",
                    models.CharField(
                        choices=[
                            ("started", "Started"),
                            ("paused", "Paused"),
                            ("resumed", "Resumed"),
                            ("completed", "Completed"),
                            ("skipped", "Skipped"),
                        ],
                        max_length=16,
                    ),
                ),
                ("occurred_at", models.DateTimeField()),
                ("idempotency_key", models.CharField(max_length=128)),
                ("source", models.CharField(default="local", max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="execution_signals",
                        to="tasks.task",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="task_execution_signals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["occurred_at", "created_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["user", "task", "occurred_at"],
                        name="task_exec_user_task_time_idx",
                    ),
                    models.Index(
                        fields=["user", "signal_type", "occurred_at"],
                        name="task_exec_user_type_time_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["user", "idempotency_key"],
                        name="task_exec_user_idempotency_uniq",
                    ),
                ],
            },
        ),
    ]
