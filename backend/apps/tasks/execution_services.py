from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction

from apps.tasks.models import (
    Task,
    TaskExecutionSignal,
    TaskExecutionSignalType,
    TaskStatus,
)
from apps.tasks.services import TaskService
from common.time import to_utc


class ExecutionSignalIdempotencyConflictError(ValueError):
    """The same idempotency key was reused for a different signal."""


@dataclass(frozen=True, slots=True)
class RecordExecutionSignalCommand:
    user: User
    task_id: UUID
    signal_type: TaskExecutionSignalType | str
    occurred_at: datetime
    idempotency_key: str
    source: str = "local"
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TaskExecutionSummary:
    task_id: UUID
    signal_count: int
    active_seconds: int
    planned_seconds: int | None
    estimated_seconds: int | None
    variance_vs_plan_seconds: int | None
    variance_vs_estimate_seconds: int | None
    evidence_status: str
    open_started_at: datetime | None
    last_signal_type: TaskExecutionSignalType | None


class TaskExecutionSignalService:
    """Application boundary for immutable, user-confirmed execution evidence."""

    @staticmethod
    @transaction.atomic
    def record(command: RecordExecutionSignalCommand) -> TaskExecutionSignal:
        if command.user.pk is None:
            raise ValueError("Execution signal user must be persisted")
        key = command.idempotency_key.strip()
        if not key:
            raise ValueError("idempotency_key cannot be blank")
        occurred_at = to_utc(command.occurred_at)
        signal_type = TaskExecutionSignalType(command.signal_type)
        task = Task.objects.select_for_update().get(pk=command.task_id, user=command.user)

        existing = TaskExecutionSignal.objects.select_for_update().filter(
            user=command.user,
            idempotency_key=key,
        ).first()
        if existing is not None:
            metadata = command.metadata or {}
            if (
                existing.task_id != task.pk
                or existing.signal_type != signal_type
                or existing.occurred_at != occurred_at
                or existing.source != command.source.strip()
                or existing.metadata != metadata
            ):
                raise ExecutionSignalIdempotencyConflictError(
                    "Idempotency key was already used for a different execution signal"
                )
            return existing

        TaskExecutionSignalService._apply_task_state(
            task=task,
            signal_type=signal_type,
            occurred_at=occurred_at,
            user=command.user,
            source=command.source.strip(),
        )
        signal = TaskExecutionSignal(
            user=command.user,
            task=task,
            signal_type=signal_type,
            occurred_at=occurred_at,
            idempotency_key=key,
            source=command.source,
            metadata=command.metadata or {},
        )
        signal.full_clean()
        signal.save(force_insert=True)
        return signal

    @staticmethod
    def list(*, user: User, task_id: UUID) -> list[TaskExecutionSignal]:
        if user.pk is None:
            raise ValueError("Execution signal user must be persisted")
        return list(
            TaskExecutionSignal.objects.filter(user=user, task_id=task_id)
            .select_related("task")
            .order_by("occurred_at", "created_at", "id")
        )

    @staticmethod
    def summary(*, user: User, task_id: UUID, now: datetime) -> TaskExecutionSummary:
        task = Task.objects.get(pk=task_id, user=user)
        signals = TaskExecutionSignalService.list(user=user, task_id=task_id)
        anchor = to_utc(now)
        active_seconds = 0
        open_started_at: datetime | None = None
        for signal in signals:
            if signal.signal_type in {
                TaskExecutionSignalType.STARTED,
                TaskExecutionSignalType.RESUMED,
            }:
                if open_started_at is None:
                    open_started_at = signal.occurred_at
            elif signal.signal_type in {
                TaskExecutionSignalType.PAUSED,
                TaskExecutionSignalType.COMPLETED,
            }:
                if open_started_at is not None:
                    active_seconds += max(
                        0,
                        int((signal.occurred_at - open_started_at).total_seconds()),
                    )
                    open_started_at = None
        if open_started_at is not None:
            active_seconds += max(0, int((anchor - open_started_at).total_seconds()))
        last_signal_type = (
            TaskExecutionSignalType(signals[-1].signal_type) if signals else None
        )
        planned_seconds = (
            int((task.planned_end_at - task.planned_start_at).total_seconds())
            if task.planned_start_at is not None and task.planned_end_at is not None
            else None
        )
        estimated_seconds = (
            task.estimated_minutes * 60 if task.estimated_minutes is not None else None
        )
        evidence_status = "recording" if open_started_at is not None else "complete"
        if not signals:
            evidence_status = "no_execution_evidence"
        return TaskExecutionSummary(
            task_id=task_id,
            signal_count=len(signals),
            active_seconds=active_seconds,
            planned_seconds=planned_seconds,
            estimated_seconds=estimated_seconds,
            variance_vs_plan_seconds=(
                active_seconds - planned_seconds
                if planned_seconds is not None and signals
                else None
            ),
            variance_vs_estimate_seconds=(
                active_seconds - estimated_seconds
                if estimated_seconds is not None and signals
                else None
            ),
            evidence_status=evidence_status,
            open_started_at=open_started_at,
            last_signal_type=last_signal_type,
        )

    @staticmethod
    def _apply_task_state(
        *,
        task: Task,
        signal_type: TaskExecutionSignalType,
        occurred_at: datetime,
        user: User,
        source: str,
    ) -> None:
        target_status: TaskStatus | None = None
        if signal_type in {
            TaskExecutionSignalType.STARTED,
            TaskExecutionSignalType.RESUMED,
        } and task.status == TaskStatus.PENDING:
            target_status = TaskStatus.IN_PROGRESS
        elif (
            signal_type == TaskExecutionSignalType.PAUSED
            and task.status == TaskStatus.IN_PROGRESS
        ):
            target_status = TaskStatus.PENDING
        elif (
            signal_type == TaskExecutionSignalType.COMPLETED
            and task.status != TaskStatus.COMPLETED
        ):
            target_status = TaskStatus.COMPLETED
        if target_status is not None:
            TaskService.change_task_state(
                user=user,
                task_id=task.pk,
                status=target_status,
                occurred_at=occurred_at,
                origin=source,
            )
