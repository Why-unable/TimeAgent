from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.tasks.models import Task, TaskPriority, TaskStatus
from common.time import to_utc


@dataclass(frozen=True, slots=True)
class CreateTaskCommand:
    user: User
    title: str
    project: str = ""
    parent_task: Task | None = None
    description: str = ""
    priority: TaskPriority | str = TaskPriority.MEDIUM
    due_at: datetime | None = None
    estimated_minutes: int | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    source: str = "local"
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class UpdateTaskCommand:
    user: User
    task_id: UUID
    changes: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TaskQuery:
    user: User
    statuses: tuple[TaskStatus | str, ...] = field(default_factory=tuple)
    due_before: datetime | None = None
    planned_starts_before: datetime | None = None
    planned_ends_after: datetime | None = None


class TaskService:
    UPDATE_FIELDS = frozenset(
        {
            "project",
            "parent_task",
            "title",
            "description",
            "priority",
            "due_at",
            "estimated_minutes",
            "source",
            "tags",
        }
    )

    @staticmethod
    @transaction.atomic
    def create_task(command: CreateTaskCommand) -> Task:
        TaskService._ensure_persisted_user(command.user)
        task = Task(
            user=command.user,
            title=command.title,
            project=command.project,
            parent_task=command.parent_task,
            description=command.description,
            priority=command.priority,
            due_at=command.due_at,
            estimated_minutes=command.estimated_minutes,
            planned_start_at=command.planned_start_at,
            planned_end_at=command.planned_end_at,
            source=command.source,
            tags=command.tags,
        )
        task.full_clean()
        task.save(force_insert=True)
        return task

    @staticmethod
    @transaction.atomic
    def update_task(command: UpdateTaskCommand) -> Task:
        TaskService._ensure_persisted_user(command.user)
        TaskService._validate_changes(command.changes)
        task = Task.objects.select_for_update().get(pk=command.task_id, user=command.user)
        for field_name, value in command.changes.items():
            setattr(task, field_name, value)
        task.full_clean()
        task.save()
        return task

    @staticmethod
    @transaction.atomic
    def complete_task(
        *,
        task_id: UUID,
        user: User,
        occurred_at: datetime | None = None,
    ) -> Task:
        TaskService._ensure_persisted_user(user)
        task = Task.objects.select_for_update().get(pk=task_id, user=user)
        if task.status == TaskStatus.COMPLETED:
            return task

        task.transition_to(TaskStatus.COMPLETED, occurred_at=occurred_at or timezone.now())
        task.full_clean()
        task.save()
        return task

    @staticmethod
    @transaction.atomic
    def cancel_task(
        *,
        task_id: UUID,
        user: User,
        occurred_at: datetime | None = None,
    ) -> Task:
        """Cancel an active task without deleting its audit history."""

        TaskService._ensure_persisted_user(user)
        task = Task.objects.select_for_update().get(pk=task_id, user=user)
        if task.status == TaskStatus.CANCELLED:
            return task

        task.transition_to(TaskStatus.CANCELLED, occurred_at=occurred_at or timezone.now())
        task.full_clean()
        task.save()
        return task

    @staticmethod
    @transaction.atomic
    def reschedule_task(
        *,
        task_id: UUID,
        user: User,
        planned_start_at: datetime | None,
        planned_end_at: datetime | None,
    ) -> Task:
        TaskService._ensure_persisted_user(user)
        task = Task.objects.select_for_update().get(pk=task_id, user=user)
        task.planned_start_at = planned_start_at
        task.planned_end_at = planned_end_at
        task.full_clean()
        task.save()
        return task

    @staticmethod
    def list_tasks(query: TaskQuery) -> list[Task]:
        TaskService._ensure_persisted_user(query.user)
        tasks = Task.objects.filter(user=query.user)
        if query.statuses:
            tasks = tasks.filter(status__in=query.statuses)
        if query.due_before is not None:
            tasks = tasks.filter(due_at__lte=to_utc(query.due_before))
        if query.planned_starts_before is not None:
            tasks = tasks.filter(planned_start_at__lt=to_utc(query.planned_starts_before))
        if query.planned_ends_after is not None:
            tasks = tasks.filter(planned_end_at__gt=to_utc(query.planned_ends_after))
        return list(tasks)

    @staticmethod
    def get_task(*, user: User, task_id: UUID) -> Task:
        TaskService._ensure_persisted_user(user)
        return Task.objects.get(pk=task_id, user=user)

    @staticmethod
    def _validate_changes(changes: Mapping[str, Any]) -> None:
        unsupported_fields = set(changes) - TaskService.UPDATE_FIELDS
        if unsupported_fields:
            fields = ", ".join(sorted(unsupported_fields))
            raise ValueError(f"Unsupported task fields: {fields}")

    @staticmethod
    def _ensure_persisted_user(user: User) -> None:
        if user.pk is None:
            raise ValueError("Task user must be persisted")
