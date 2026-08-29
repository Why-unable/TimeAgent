import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("time_memory", "0003_alter_schedulechange_entity_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="TimeDecisionFeedback",
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
                ("category", models.CharField(max_length=64)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("accept", "Accept"),
                            ("override", "Override"),
                            ("disable", "Disable"),
                        ],
                        max_length=16,
                    ),
                ),
                ("value", models.JSONField(blank=True, default=dict)),
                ("idempotency_key", models.CharField(max_length=128)),
                ("source", models.CharField(default="web", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="time_decision_feedback",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["user", "category", "created_at"],
                        name="time_decision_feedback_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "idempotency_key"),
                        name="time_decision_feedback_user_key_uniq",
                    )
                ],
            },
        ),
    ]
