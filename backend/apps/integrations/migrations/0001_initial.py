import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.preferences.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CalendarSyncConnection",
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
                ("provider_name", models.CharField(max_length=64)),
                ("account_reference", models.CharField(max_length=255)),
                ("calendar_id", models.CharField(max_length=255)),
                ("calendar_name", models.CharField(max_length=255)),
                (
                    "timezone",
                    models.CharField(
                        max_length=64,
                        validators=[apps.preferences.models.validate_iana_timezone],
                    ),
                ),
                ("enabled", models.BooleanField(default=True)),
                ("sync_cursor", models.CharField(blank=True, max_length=2048)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ready", "Ready"),
                            ("error", "Error"),
                            ("disabled", "Disabled"),
                        ],
                        default="ready",
                        max_length=16,
                    ),
                ),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calendar_sync_connections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["provider_name", "calendar_name", "id"],
                "indexes": [
                    models.Index(
                        fields=["user", "enabled", "status"],
                        name="calendar_sync_user_status_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["user", "provider_name", "account_reference", "calendar_id"],
                        name="calendar_sync_connection_identity_uniq",
                    ),
                ],
            },
        ),
    ]
