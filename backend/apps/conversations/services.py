from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.conversations.models import (
    AgentEvent,
    AgentRun,
    AgentRunStatus,
    Conversation,
    ToolCallAudit,
    ToolCallStatus,
)


class RunCancellationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StartRunCommand:
    conversation: Conversation
    operation_id: UUID
    request_id: str
    message: str


class ConversationService:
    @staticmethod
    def create(*, user: User, title: str = "") -> Conversation:
        if user.pk is None:
            raise ValueError("Conversation user must be persisted")
        return Conversation.objects.create(user=user, title=title.strip())

    @staticmethod
    def get(*, user: User, conversation_id: UUID) -> Conversation:
        if user.pk is None:
            raise ValueError("Conversation user must be persisted")
        return Conversation.objects.get(pk=conversation_id, user=user)

    @staticmethod
    def get_with_runs(*, user: User, conversation_id: UUID) -> Conversation:
        if user.pk is None:
            raise ValueError("Conversation user must be persisted")
        return Conversation.objects.prefetch_related("runs").get(
            pk=conversation_id,
            user=user,
        )

    @staticmethod
    def list(*, user: User) -> list[Conversation]:
        if user.pk is None:
            raise ValueError("Conversation user must be persisted")
        return list(Conversation.objects.filter(user=user))


class AgentRunService:
    @staticmethod
    @transaction.atomic
    def start(command: StartRunCommand) -> AgentRun:
        message = command.message.strip()
        request_id = command.request_id.strip()
        if not message or not request_id:
            raise ValueError("message and request_id cannot be empty")
        run, created = AgentRun.objects.get_or_create(
            operation_id=command.operation_id,
            defaults={
                "conversation": command.conversation,
                "request_id": request_id,
                "input_message": message,
            },
        )
        if run.conversation_id != command.conversation.pk or run.input_message != message:
            raise ValueError("operation_id already belongs to a different run")
        if created:
            conversation = Conversation.objects.select_for_update().get(pk=command.conversation.pk)
            if not conversation.title:
                conversation.title = message[:80]
            conversation.updated_at = timezone.now()
            conversation.save(update_fields=["title", "updated_at"])
        return run

    @staticmethod
    @transaction.atomic
    def reserve_execution_task(run: AgentRun, task_id: str) -> bool:
        normalized_task_id = task_id.strip()
        if not normalized_task_id:
            raise ValueError("task_id cannot be empty")
        locked = AgentRun.objects.select_for_update().get(pk=run.pk)
        if locked.status != AgentRunStatus.PENDING:
            return False
        if locked.execution_task_id and locked.execution_task_id != normalized_task_id:
            return False
        if not locked.execution_task_id:
            locked.execution_task_id = normalized_task_id
            locked.save(update_fields=["execution_task_id"])
        return True

    @staticmethod
    @transaction.atomic
    def release_execution_task(run: AgentRun, task_id: str) -> None:
        locked = AgentRun.objects.select_for_update().get(pk=run.pk)
        if locked.status == AgentRunStatus.PENDING and locked.execution_task_id == task_id:
            locked.execution_task_id = ""
            locked.save(update_fields=["execution_task_id"])

    @staticmethod
    @transaction.atomic
    def wait_for_approval(run: AgentRun) -> AgentRun:
        locked = AgentRun.objects.select_for_update().get(pk=run.pk)
        if locked.status == AgentRunStatus.CANCELLED:
            return locked
        locked.status = AgentRunStatus.WAITING_APPROVAL
        locked.execution_task_id = ""
        locked.save(update_fields=["status", "execution_task_id"])
        return locked

    @staticmethod
    @transaction.atomic
    def reserve_resume_task(run: AgentRun, task_id: str) -> bool:
        normalized_task_id = task_id.strip()
        if not normalized_task_id:
            raise ValueError("task_id cannot be empty")
        locked = AgentRun.objects.select_for_update().get(pk=run.pk)
        if locked.status != AgentRunStatus.WAITING_APPROVAL:
            return False
        if locked.execution_task_id and locked.execution_task_id != normalized_task_id:
            return False
        locked.execution_task_id = normalized_task_id
        locked.save(update_fields=["execution_task_id"])
        return True

    @staticmethod
    @transaction.atomic
    def release_resume_task(run: AgentRun, task_id: str) -> None:
        locked = AgentRun.objects.select_for_update().get(pk=run.pk)
        if locked.status == AgentRunStatus.WAITING_APPROVAL and locked.execution_task_id == task_id:
            locked.execution_task_id = ""
            locked.save(update_fields=["execution_task_id"])

    @staticmethod
    @transaction.atomic
    def claim_for_resume(run: AgentRun, *, task_id: str) -> AgentRun | None:
        locked = AgentRun.objects.select_for_update().get(pk=run.pk)
        if locked.status != AgentRunStatus.WAITING_APPROVAL:
            return None
        if locked.execution_task_id != task_id.strip():
            return None
        locked.status = AgentRunStatus.RUNNING
        locked.save(update_fields=["status"])
        AgentRunService.append_event(locked, "agent.resumed", {"run_id": str(locked.pk)})
        return locked

    @staticmethod
    @transaction.atomic
    def claim_for_execution(run: AgentRun, *, task_id: str | None = None) -> AgentRun | None:
        locked = AgentRun.objects.select_for_update().get(pk=run.pk)
        normalized_task_id = task_id.strip() if task_id else ""
        if locked.status == AgentRunStatus.RUNNING:
            if normalized_task_id and locked.execution_task_id == normalized_task_id:
                return locked
            return None
        if locked.status != AgentRunStatus.PENDING:
            return None
        if locked.execution_task_id and locked.execution_task_id != normalized_task_id:
            return None
        locked.status = AgentRunStatus.RUNNING
        locked.started_at = timezone.now()
        locked.save(update_fields=["status", "started_at"])
        AgentRunService.append_event(locked, "agent.started", {"run_id": str(locked.pk)})
        return locked

    @staticmethod
    def mark_running(run: AgentRun) -> AgentRun:
        """Compatibility helper for direct execution and focused service tests."""

        claimed = AgentRunService.claim_for_execution(run)
        if claimed is not None:
            return claimed
        return AgentRun.objects.get(pk=run.pk)

    @staticmethod
    @transaction.atomic
    def complete(run: AgentRun, final_response: str) -> AgentRun:
        locked = AgentRun.objects.select_for_update().get(pk=run.pk)
        if locked.status == AgentRunStatus.CANCELLED:
            return locked
        locked.status = AgentRunStatus.COMPLETED
        locked.final_response = final_response
        locked.completed_at = timezone.now()
        locked.save(update_fields=["status", "final_response", "completed_at"])
        AgentRunService.append_event(locked, "message.completed", {"content": final_response})
        return locked

    @staticmethod
    @transaction.atomic
    def fail(run: AgentRun, error: Exception) -> AgentRun:
        locked = AgentRun.objects.select_for_update().get(pk=run.pk)
        if locked.status == AgentRunStatus.CANCELLED:
            return locked
        locked.status = AgentRunStatus.FAILED
        locked.error = "The agent run could not be completed"
        locked.completed_at = timezone.now()
        locked.save(update_fields=["status", "error", "completed_at"])
        AgentRunService.append_event(
            locked, "run.failed", {"error": "The agent run could not be completed"}
        )
        return locked

    @staticmethod
    @transaction.atomic
    def cancel(*, user: User, run_id: UUID) -> AgentRun:
        run = AgentRun.objects.select_for_update().get(
            pk=run_id,
            conversation__user=user,
        )
        if run.status in {AgentRunStatus.COMPLETED, AgentRunStatus.FAILED}:
            raise RunCancellationError("A finished run cannot be cancelled")
        if run.status != AgentRunStatus.CANCELLED:
            run.status = AgentRunStatus.CANCELLED
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "completed_at"])
            AgentRunService.append_event(run, "run.cancelled", {})
        return run

    @staticmethod
    def get(*, user: User, run_id: UUID) -> AgentRun:
        return AgentRun.objects.get(pk=run_id, conversation__user=user)

    @staticmethod
    @transaction.atomic
    def append_event(run: AgentRun, event_type: str, payload: dict[str, Any]) -> AgentEvent:
        locked_run = AgentRun.objects.select_for_update().get(pk=run.pk)
        maximum = AgentEvent.objects.filter(run=locked_run).aggregate(value=Max("sequence"))[
            "value"
        ]
        return AgentEvent.objects.create(
            run=locked_run,
            sequence=(maximum or 0) + 1,
            event_type=event_type,
            payload=payload,
        )

    @staticmethod
    def events_after(*, user: User, run_id: UUID, cursor: int) -> list[AgentEvent]:
        return list(
            AgentEvent.objects.filter(
                run_id=run_id,
                run__conversation__user=user,
                sequence__gt=cursor,
            )
        )

    @staticmethod
    def is_cancelled(run_id: UUID) -> bool:
        return AgentRun.objects.filter(pk=run_id, status=AgentRunStatus.CANCELLED).exists()


class ToolAuditService:
    @staticmethod
    @transaction.atomic
    def begin(
        *,
        run_id: str,
        user: User,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        risk_level: str,
    ) -> tuple[ToolCallAudit, bool]:
        audit, created = ToolCallAudit.objects.get_or_create(
            run_id=run_id,
            tool_call_id=tool_call_id,
            defaults={
                "user": user,
                "tool_name": tool_name,
                "arguments": arguments,
                "risk_level": risk_level,
            },
        )
        return audit, created

    @staticmethod
    def complete(audit: ToolCallAudit, result: Any) -> None:
        audit.status = ToolCallStatus.COMPLETED
        audit.result = result
        audit.completed_at = timezone.now()
        audit.save(update_fields=["status", "result", "completed_at"])

    @staticmethod
    def fail(audit: ToolCallAudit, error: Exception) -> None:
        audit.status = ToolCallStatus.FAILED
        audit.error = f"{type(error).__name__}: {error}"[:4000]
        audit.completed_at = timezone.now()
        audit.save(update_fields=["status", "error", "completed_at"])
