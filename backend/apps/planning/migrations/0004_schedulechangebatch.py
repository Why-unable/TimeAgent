import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("planning", "0003_automationpolicy")]
    operations = [
        migrations.CreateModel(
            name="ScheduleChangeBatch",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("operation_id", models.UUIDField(unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("applied", "Applied"),
                            ("reverted", "Reverted"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("before_snapshot", models.JSONField(default=list)),
                ("after_snapshot", models.JSONField(default=list)),
                ("failure_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("reverted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="planning.automationpolicy"
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["user", "status", "created_at"],
                        name="planning_sc_user_id_7e1b9c_idx",
                    )
                ],
            },
        )
    ]
