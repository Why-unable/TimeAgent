import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("auth", "0012_alter_user_first_name_max_length")]
    operations = [
        migrations.CreateModel(
            name="TemporalInsight",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("kind", models.CharField(max_length=64)),
                ("severity", models.CharField(max_length=16)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("snoozed", "Snoozed"),
                            ("dismissed", "Dismissed"),
                            ("actioned", "Actioned"),
                            ("expired", "Expired"),
                        ],
                        default="open",
                        max_length=16,
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("summary", models.TextField()),
                ("evidence", models.JSONField(blank=True, default=dict)),
                ("deduplication_key", models.CharField(max_length=255)),
                ("detected_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("snoozed_until", models.DateTimeField(blank=True, null=True)),
                ("acted_at", models.DateTimeField(blank=True, null=True)),
                ("attention_decision", models.CharField(default="STORE", max_length=32)),
                ("attention_reason", models.CharField(blank=True, max_length=128)),
                ("attention_decided_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="temporal_insights",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-detected_at", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "deduplication_key"), name="insight_user_dedup_uniq"
                    )
                ],
                "indexes": [
                    models.Index(
                        fields=["user", "status", "expires_at"],
                        name="insight_user_status_expiry_idx",
                    )
                ],
            },
        )
    ]
