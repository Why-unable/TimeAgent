import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="LLMCallAudit",
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
                ("request_id", models.CharField(db_index=True, max_length=128)),
                ("agent_run_id", models.CharField(blank=True, db_index=True, max_length=64)),
                ("component", models.CharField(max_length=32)),
                ("model_name", models.CharField(max_length=128)),
                ("status", models.CharField(max_length=16)),
                ("usage_source", models.CharField(max_length=16)),
                ("input_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("output_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("total_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("memory_prompt_tokens", models.PositiveIntegerField(default=0)),
                ("memory_prompt_ratio", models.FloatField(blank=True, null=True)),
                ("duration_ms", models.PositiveIntegerField()),
                ("error_type", models.CharField(blank=True, max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="llmcallaudit",
            index=models.Index(
                fields=["component", "-created_at"],
                name="llm_component_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="llmcallaudit",
            index=models.Index(fields=["status", "-created_at"], name="llm_status_created_idx"),
        ),
        migrations.AddIndex(
            model_name="llmcallaudit",
            index=models.Index(fields=["model_name", "-created_at"], name="llm_model_created_idx"),
        ),
    ]
