from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.accounts.services import GuestAccountPolicyService
from apps.tasks.models import Task, TaskPriority, TaskStatus
from common.database_locks import lock_user_schedule_writes
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
    origin: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateTaskCommand:
    user: User
    task_id: UUID
    changes: Mapping[str, Any]
    expected_version: int | None = None
    origin: str = "web"


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
        GuestAccountPolicyService.assert_resource_creation_allowed(command.user, "task")
        lock_user_schedule_writes(command.user)
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
        from apps.reminders.scheduling import ReminderScheduleService

        ReminderScheduleService.sync_task_reminders(task=task)
        TaskService._record_change(
            task=task,
            operation="created",
            origin=command.origin or ("agent" if task.source == "agent" else "web"),
            old_snapshot={},
        )
        return task

    @staticmethod
    @transaction.atomic
    def create_tasks(*, commands: list[CreateTaskCommand]) -> list[Task]:
        """Create a finite task batch atomically through the normal task invariant."""

        if not commands:
            raise ValueError("At least one task is required")
        user = commands[0].user
        if any(command.user.pk != user.pk for command in commands):
            raise ValueError("All batch tasks must belong to the same user")
        return [TaskService.create_task(command) for command in commands]

    @staticmethod
    @transaction.atomic
    def update_task(command: UpdateTaskCommand) -> Task:
        TaskService._ensure_persisted_user(command.user)
        lock_user_schedule_writes(command.user)
        TaskService._validate_changes(command.changes)
        task = Task.objects.select_for_update().get(pk=command.task_id, user=command.user)
        if command.expected_version is not None:
            TaskService._ensure_version(task, command.expected_version)
        old_snapshot = TaskService._snapshot(task)
        for field_name, value in command.changes.items():
            setattr(task, field_name, value)
        task.full_clean()
        task.version += 1
        task.save()
        from apps.reminders.scheduling import ReminderScheduleService

        ReminderScheduleService.sync_task_reminders(task=task)
        TaskService._record_change(
            task=task,
            operation="updated",
            origin=command.origin,
            old_snapshot=old_snapshot,
        )
        return task

    @staticmethod
    @transaction.atomic
    def complete_task(
        *,
        task_id: UUID,
        user: User,
        occurred_at: datetime | None = None,
        origin: str = "web",
    ) -> Task:
        TaskService._ensure_persisted_user(user)
        lock_user_schedule_writes(user)
        task = Task.objects.select_for_update().get(pk=task_id, user=user)
        if task.status == TaskStatus.COMPLETED:
            return task

        old_snapshot = TaskService._snapshot(task)
        task.transition_to(TaskStatus.COMPLETED, occurred_at=occurred_at or timezone.now())
        task.version += 1
        task.full_clean()
        task.save()
        from apps.reminders.scheduling import ReminderScheduleService

        ReminderScheduleService.cancel_task_reminders(task=task)
        TaskService._record_change(
            task=task,
            operation="completed",
            origin=origin,
            old_snapshot=old_snapshot,
            occurred_at=task.completed_at,
        )
        return task

    @staticmethod
    @transaction.atomic
    def cancel_task(
        *,
        task_id: UUID,
        user: User,
        occurred_at: datetime | None = None,
        origin: str = "web",
    ) -> Task:
        """Cancel an active task without deleting its audit history."""

        TaskService._ensure_persisted_user(user)
        lock_user_schedule_writes(user)
        task = Task.objects.select_for_update().get(pk=task_id, user=user)
        if task.status == TaskStatus.CANCELLED:
            return task

        old_snapshot = TaskService._snapshot(task)
        task.transition_to(TaskStatus.CANCELLED, occurred_at=occurred_at or timezone.now())
        task.version += 1
        task.full_clean()
        task.save()
        from apps.reminders.scheduling import ReminderScheduleService

        ReminderScheduleService.cancel_task_reminders(task=task)
        TaskService._record_change(
            task=task,
            operation="cancelled",
            origin=origin,
            old_snapshot=old_snapshot,
            occurred_at=occurred_at,
        )
        return task

    @staticmethod
    @transaction.atomic
    def reschedule_task(
        *,
        task_id: UUID,
        user: User,
        planned_start_at: datetime | None,
        planned_end_at: datetime | None,
        origin: str = "web",
    ) -> Task:
        TaskService._ensure_persisted_user(user)
        lock_user_schedule_writes(user)
        task = Task.objects.select_for_update().get(pk=task_id, user=user)
        old_snapshot = TaskService._snapshot(task)
        task.planned_start_at = planned_start_at
        task.planned_end_at = planned_end_at
        task.version += 1
        task.full_clean()
        task.save()
        from apps.reminders.scheduling import ReminderScheduleService

        ReminderScheduleService.sync_task_reminders(task=task)
        TaskService._record_change(
            task=task,
            operation="updated",
            origin=origin,
            old_snapshot=old_snapshot,
        )
        return task

    @staticmethod
    @transaction.atomic
    def change_task_state(
        *,
        task_id: UUID,
        user: User,
        status: TaskStatus | str,
        occurred_at: datetime,
        origin: str = "web",
    ) -> Task:
        """Apply a valid task state-machine transition and synchronise derived reminders."""

        TaskService._ensure_persisted_user(user)
        lock_user_schedule_writes(user)
        task = Task.objects.select_for_update().get(pk=task_id, user=user)
        normalized_status = TaskStatus(status)
        if task.status == normalized_status:
            return task
        old_snapshot = TaskService._snapshot(task)
        task.transition_to(normalized_status, occurred_at=occurred_at)
        task.version += 1
        task.full_clean()
        task.save()
        from apps.reminders.scheduling import ReminderScheduleService

        if normalized_status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
            ReminderScheduleService.cancel_task_reminders(task=task)
        else:
            ReminderScheduleService.sync_task_reminders(task=task)
        TaskService._record_change(
            task=task,
            operation=(
                "completed"
                if normalized_status == TaskStatus.COMPLETED
                else "cancelled"
                if normalized_status == TaskStatus.CANCELLED
                else "updated"
            ),
            origin=origin,
            old_snapshot=old_snapshot,
            occurred_at=occurred_at,
        )
        return task

    @staticmethod
    @transaction.atomic
    def change_tasks_state(
        *,
        user: User,
        items: list[tuple[UUID, int]],
        status: TaskStatus | str,
        occurred_at: datetime,
        origin: str = "web",
    ) -> list[Task]:
        """Atomically transition a versioned, finite set of tasks."""

        TaskService._ensure_persisted_user(user)
        lock_user_schedule_writes(user)
        if not items:
            raise ValueError("At least one task is required")
        task_ids = [task_id for task_id, _ in items]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("Task batch must not contain duplicate task IDs")
        locked = {
            task.pk: task
            for task in Task.objects.select_for_update().filter(user=user, pk__in=task_ids)
        }
        if len(locked) != len(items):
            raise ValueError("Every task must belong to the current user")
        normalized_status = TaskStatus(status)
        tasks: list[Task] = []
        old_snapshots: dict[UUID, dict[str, Any]] = {}
        for task_id, expected_version in items:
            task = locked[task_id]
            TaskService._ensure_version(task, expected_version)
            if task.status != normalized_status:
                old_snapshots[task.pk] = TaskService._snapshot(task)
                task.transition_to(normalized_status, occurred_at=occurred_at)
                task.version += 1
                task.full_clean()
                task.save()
            tasks.append(task)
        from apps.reminders.scheduling import ReminderScheduleService

        for task in tasks:
            if normalized_status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
                ReminderScheduleService.cancel_task_reminders(task=task)
            else:
                ReminderScheduleService.sync_task_reminders(task=task)
            if task.pk in old_snapshots:
                TaskService._record_change(
                    task=task,
                    operation=(
                        "completed"
                        if normalized_status == TaskStatus.COMPLETED
                        else "cancelled"
                        if normalized_status == TaskStatus.CANCELLED
                        else "updated"
                    ),
                    origin=origin,
                    old_snapshot=old_snapshots[task.pk],
                    occurred_at=occurred_at,
                )
        return tasks

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
    def _ensure_version(task: Task, expected_version: int) -> None:
        if task.version != expected_version:
            raise ValueError(
                f"Task version conflict: expected {expected_version}, current {task.version}"
            )

    @staticmethod
    def _ensure_persisted_user(user: User) -> None:
        if user.pk is None:
            raise ValueError("Task user must be persisted")

    @staticmethod
    def _snapshot(task: Task) -> dict[str, Any]:
        from apps.time_memory.event_handler import json_snapshot

        return json_snapshot(
            task,
            (
                "title",
                "status",
                "due_at",
                "planned_start_at",
                "planned_end_at",
                "completed_at",
                "source",
            ),
        )

    @staticmethod
    def _record_change(
        *,
        task: Task,
        operation: str,
        origin: str,
        old_snapshot: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> None:
        from apps.time_memory.event_handler import record_schedule_change

        record_schedule_change(
            user=task.user,
            entity_type="task",
            entity_id=task.pk,
            operation=operation,
            source=origin,
            old_snapshot=old_snapshot,
            new_snapshot=TaskService._snapshot(task),
            occurred_at=occurred_at,
        )
