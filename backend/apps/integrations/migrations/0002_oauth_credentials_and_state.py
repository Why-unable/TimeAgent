import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CalendarOAuthCredential",
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
                ("encrypted_token_payload", models.TextField()),
                ("access_token_expires_at", models.DateTimeField(blank=True, null=True)),
                ("scopes", models.JSONField(blank=True, default=list)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("last_refreshed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calendar_oauth_credentials",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "provider_name", "account_reference"),
                        name="calendar_oauth_credential_identity_uniq",
                    )
                ]
            },
        ),
        migrations.CreateModel(
            name="CalendarOAuthState",
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
                ("state_digest", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calendar_oauth_states",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["provider_name", "expires_at", "consumed_at"],
                        name="cal_oauth_state_lookup_idx",
                    )
                ]
            },
        ),
    ]
