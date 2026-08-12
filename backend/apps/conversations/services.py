import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.services import GuestAccountPolicyService
from apps.conversations.models import (
    AgentEvent,
    AgentRun,
    AgentRunStatus,
    Conversation,
    ConversationKind,
    ToolCallAudit,
    ToolCallStatus,
)


class RunCancellationError(ValueError):
    pass


class StaleAgentRunError(TimeoutError):
    pass


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentRunFailure:
    code: str
    message: str
    retryable: bool


def classify_agent_run_failure(error: Exception) -> AgentRunFailure:
    if isinstance(error, StaleAgentRunError):
        return AgentRunFailure(
            "agent_execution_stale",
            "本次处理因执行进程异常中断，请重新发送请求。",
            True,
        )
    name = type(error).__name__.lower()
    status_code = getattr(error, "status_code", None)
    text = str(error).lower()
    database_error = getattr(error, "__cause__", None)
    sqlstate = getattr(database_error, "sqlstate", None)
    if sqlstate == "40P01" or "deadlock detected" in text:
        return AgentRunFailure(
            "database_concurrency_conflict",
            "写入时发生并发冲突，请重试未完成的操作。",
            True,
        )
    if status_code in {401, 403} or "authentication" in name or "invalid api key" in text:
        return AgentRunFailure(
            "model_authentication_failed", "模型服务认证失败，请联系管理员检查 API Key。", False
        )
    if status_code == 429 or "ratelimit" in name or "rate limit" in text:
        return AgentRunFailure("model_rate_limited", "模型服务当前请求过多，请稍后重试。", True)
    if "timeout" in name or isinstance(error, TimeoutError):
        return AgentRunFailure("model_timeout", "模型服务响应超时，请检查网络后重试。", True)
    if any(token in name for token in ("connection", "connect", "network")):
        return AgentRunFailure(
            "model_unreachable", "暂时无法连接模型服务，请检查网络或服务地址。", True
        )
    if "empty final ai message" in text or "without a final ai message" in text:
        return AgentRunFailure(
            "empty_model_response", "模型没有返回有效回复，请重新发送或稍后重试。", True
        )
    if "recursion" in name or "limit" in text:
        return AgentRunFailure(
            "agent_limit_reached", "本次请求达到处理上限，请缩短或拆分请求后重试。", True
        )
    return AgentRunFailure("agent_internal_error", "处理请求时发生内部错误，请稍后重试。", True)


@dataclass(frozen=True, slots=True)
class StartRunCommand:
    conversation: Conversation
    operation_id: UUID
    request_id: str
    message: str
    trigger_type: str = "user_message"
    trigger_payload: dict[str, Any] | None = None
    synthetic_input: bool = False
    anchor_at: datetime | None = None
    anchor_timezone: str | None = None


class ConversationService:
    @staticmethod
    @transaction.atomic
    def create(
        *,
        user: User,
        title: str = "",
        kind: str = ConversationKind.CHAT,
    ) -> Conversation:
        if user.pk is None:
            raise ValueError("Conversation user must be persisted")
        if kind not in ConversationKind.values:
            raise ValueError("Unknown conversation kind")
        GuestAccountPolicyService.assert_resource_creation_allowed(user, "conversation")
        return Conversation.objects.create(user=user, title=title.strip(), kind=kind)

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
        GuestAccountPolicyService.assert_agent_run_allowed(
            command.conversation.user,
            operation_id=command.operation_id,
        )
        anchor_at = command.anchor_at or timezone.now()
        if anchor_at.tzinfo is None or anchor_at.utcoffset() is None:
            raise ValueError("anchor_at must be timezone-aware")
        anchor_timezone = command.anchor_timezone
        if anchor_timezone is None:
            from django.conf import settings

            from apps.preferences.services import UserPreferenceService

            preference = UserPreferenceService.get_for_user(command.conversation.user)
            anchor_timezone = preference.timezone if preference else settings.DEFAULT_USER_TIMEZONE
        from common.time import to_utc, validate_timezone

        validate_timezone(anchor_timezone)
        run, created = AgentRun.objects.get_or_create(
            operation_id=command.operation_id,
            defaults={
                "conversation": command.conversation,
                "request_id": request_id,
                "input_message": message,
                "trigger_type": command.trigger_type,
                "trigger_payload": command.trigger_payload or {},
                "synthetic_input": command.synthetic_input,
                "anchor_at": to_utc(anchor_at),
                "anchor_timezone": anchor_timezone,
            },
        )
        if (
            run.conversation_id != command.conversation.pk
            or run.input_message != message
            or run.trigger_type != command.trigger_type
            or run.trigger_payload != (command.trigger_payload or {})
            or run.synthetic_input != command.synthetic_input
        ):
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
        if locked.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }:
            return locked
        failure = classify_agent_run_failure(error)
        completed_write_tools = list(
            ToolCallAudit.objects.filter(run=locked, status=ToolCallStatus.COMPLETED)
            .exclude(risk_level="read")
            .values_list("tool_name", flat=True)
        )
        partial_success = bool(completed_write_tools)
        message = failure.message
        if partial_success:
            message = (
                "本次请求仅部分完成：部分日程、任务或提醒已经保存，但仍有操作失败。"
                f"失败原因：{failure.message}请先查看相应页面确认结果，再重试未完成的部分。"
            )
        logger.exception(
            "agent_run_failed",
            extra={
                "agent_run_id": str(locked.pk),
                "request_id": locked.request_id,
                "error_code": failure.code,
                "partial_success": partial_success,
                "completed_write_tools": completed_write_tools,
            },
        )
        locked.status = AgentRunStatus.FAILED
        locked.error = message
        locked.completed_at = timezone.now()
        locked.save(update_fields=["status", "error", "completed_at"])
        AgentRunService.append_event(
            locked,
            "run.failed",
            {
                "error": message,
                "error_code": failure.code,
                "retryable": failure.retryable,
                "partial_success": partial_success,
                "completed_write_tools": completed_write_tools,
                "request_id": locked.request_id,
            },
        )
        return locked

    @staticmethod
    def fail_stale_runs(*, cutoff: datetime, batch_size: int = 100) -> int:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        run_ids = list(
            AgentRun.objects.filter(
                status__in=[AgentRunStatus.PENDING, AgentRunStatus.RUNNING],
                created_at__lt=cutoff,
            )
            .order_by("created_at", "id")
            .values_list("id", flat=True)[:batch_size]
        )
        recovered = 0
        for run_id in run_ids:
            run = AgentRun.objects.get(pk=run_id)
            result = AgentRunService.fail(run, StaleAgentRunError("Agent run exceeded deadline"))
            if result.status == AgentRunStatus.FAILED:
                recovered += 1
        return recovered

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
    def record_temporal_resolution(*, run_id: UUID, payload: dict[str, Any]) -> AgentEvent:
        run = AgentRun.objects.get(pk=run_id)
        return AgentRunService.append_event(run, "temporal.resolved", payload)

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
