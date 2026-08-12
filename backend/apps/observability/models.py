import uuid

from django.db import models


class LLMCallAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.CharField(max_length=128, db_index=True)
    agent_run_id = models.CharField(max_length=64, blank=True, db_index=True)
    component = models.CharField(max_length=32)
    model_name = models.CharField(max_length=128)
    status = models.CharField(max_length=16)
    usage_source = models.CharField(max_length=16)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    total_tokens = models.PositiveIntegerField(null=True, blank=True)
    memory_prompt_tokens = models.PositiveIntegerField(default=0)
    memory_prompt_ratio = models.FloatField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField()
    error_type = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["component", "-created_at"], name="llm_component_created_idx"),
            models.Index(fields=["status", "-created_at"], name="llm_status_created_idx"),
            models.Index(fields=["model_name", "-created_at"], name="llm_model_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.component}:{self.model_name}:{self.status}"
