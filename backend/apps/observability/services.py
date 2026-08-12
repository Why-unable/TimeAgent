from dataclasses import dataclass

from apps.observability.models import LLMCallAudit


@dataclass(frozen=True, slots=True)
class RecordLLMCallCommand:
    request_id: str
    agent_run_id: str
    component: str
    model_name: str
    status: str
    usage_source: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    memory_prompt_tokens: int
    memory_prompt_ratio: float | None
    duration_ms: int
    error_type: str = ""


class LLMCallAuditService:
    @staticmethod
    def record(command: RecordLLMCallCommand) -> LLMCallAudit:
        request_id = command.request_id.strip()[:128] or "-"
        component = command.component.strip()[:32]
        model_name = command.model_name.strip()[:128] or "unknown"
        if not component:
            raise ValueError("component cannot be empty")
        if command.status not in {"completed", "failed"}:
            raise ValueError("status must be completed or failed")
        if command.usage_source not in {"provider", "estimated", "unavailable"}:
            raise ValueError("unknown usage source")
        for value in (
            command.input_tokens,
            command.output_tokens,
            command.total_tokens,
            command.memory_prompt_tokens,
            command.duration_ms,
        ):
            if value is not None and value < 0:
                raise ValueError("token counts and duration cannot be negative")
        if command.memory_prompt_ratio is not None and not 0 <= command.memory_prompt_ratio <= 1:
            raise ValueError("memory prompt ratio must be between zero and one")
        return LLMCallAudit.objects.create(
            request_id=request_id,
            agent_run_id=command.agent_run_id.strip()[:64],
            component=component,
            model_name=model_name,
            status=command.status,
            usage_source=command.usage_source,
            input_tokens=command.input_tokens,
            output_tokens=command.output_tokens,
            total_tokens=command.total_tokens,
            memory_prompt_tokens=command.memory_prompt_tokens,
            memory_prompt_ratio=command.memory_prompt_ratio,
            duration_ms=command.duration_ms,
            error_type=command.error_type.strip()[:128],
        )
