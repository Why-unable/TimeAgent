import uuid

import django.db.models.deletion
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SchedulePlan",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("strategy", models.CharField(max_length=32)),
                ("items", models.JSONField(default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("applied", "Applied"),
                            ("superseded", "Superseded"),
                        ],
                        default="draft",
                        max_length=16,
                    ),
                ),
                (
                    "version",
                    models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)]),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="auth.user"),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["user", "status", "created_at"],
                        name="planning_sc_user_id_3b1f5d_idx",
                    )
                ]
            },
        ),
    ]
