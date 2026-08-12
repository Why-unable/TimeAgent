from django.contrib import admin

from apps.observability.models import LLMCallAudit


@admin.register(LLMCallAudit)
class LLMCallAuditAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "created_at",
        "component",
        "model_name",
        "status",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "memory_prompt_tokens",
        "memory_prompt_ratio",
        "duration_ms",
        "request_id",
    )
    list_filter = ("component", "model_name", "status", "usage_source")
    search_fields = ("request_id", "agent_run_id")
    readonly_fields = tuple(field.name for field in LLMCallAudit._meta.fields)

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False
