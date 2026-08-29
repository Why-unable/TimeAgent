import uuid

import django.db.models.deletion
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("planning", "0002_rename_schedule_plan_index")]
    operations = [
        migrations.CreateModel(
            name="AutomationPolicy",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("enabled", models.BooleanField(default=False)),
                ("allow_task_reschedule", models.BooleanField(default=False)),
                (
                    "max_moves_per_run",
                    models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)]),
                ),
                ("requires_approval", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="automation_policies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["name", "created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "name"), name="automation_policy_user_name_uniq"
                    )
                ],
            },
        )
    ]
