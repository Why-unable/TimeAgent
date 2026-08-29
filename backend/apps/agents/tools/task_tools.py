from datetime import datetime
from uuid import UUID

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import model_dict, require_actor, require_writable
from apps.tasks.execution_services import (
    RecordExecutionSignalCommand,
    TaskExecutionSignalService,
)
from apps.tasks.services import CreateTaskCommand, TaskQuery, TaskService, UpdateTaskCommand

TASK_FIELDS = (
    "id",
    "title",
    "description",
    "project",
    "status",
    "priority",
    "due_at",
    "estimated_minutes",
    "planned_start_at",
    "planned_end_at",
    "tags",
    "version",
)


class TaskDraftInput(BaseModel):
    """Schema for one task in an atomic create-task batch."""

    title: str
    description: str = ""
    project: str = ""
    priority: str = "medium"
    due_at: datetime | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    estimated_minutes: int | None = None
    tags: list[str] = Field(default_factory=list)


@tool
def list_tasks(
    statuses: list[str] | None = None,
    due_before: datetime | None = None,
    runtime: ToolRuntime[RuntimeContext] = None,  # type: ignore[assignment]
) -> list[dict[str, object]]:
    """List the current user's tasks with optional status and due-time filters."""

    tasks = TaskService.list_tasks(
        TaskQuery(
            user=require_actor(runtime),
            statuses=tuple(statuses or ()),
            due_before=due_before,
        )
    )
    return [model_dict(task, TASK_FIELDS) for task in tasks]


@tool
def get_task(task_id: UUID, runtime: ToolRuntime[RuntimeContext]) -> dict[str, object]:
    """Get one task owned by the current user."""

    task = TaskService.get_task(user=require_actor(runtime), task_id=task_id)
    return model_dict(task, TASK_FIELDS)


@tool
def get_task_execution_summary(
    task_id: UUID,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Get recorded task execution time and its variance from plan and estimate."""

    summary = TaskExecutionSignalService.summary(
        user=require_actor(runtime),
        task_id=task_id,
        now=runtime.context.current_datetime,
    )
    return {
        "task_id": str(summary.task_id),
        "signal_count": summary.signal_count,
        "active_seconds": summary.active_seconds,
        "planned_seconds": summary.planned_seconds,
        "estimated_seconds": summary.estimated_seconds,
        "variance_vs_plan_seconds": summary.variance_vs_plan_seconds,
        "variance_vs_estimate_seconds": summary.variance_vs_estimate_seconds,
        "evidence_status": summary.evidence_status,
        "open_started_at": (
            summary.open_started_at.isoformat() if summary.open_started_at is not None else None
        ),
        "last_signal_type": summary.last_signal_type,
    }


@tool
def create_task(
    title: str,
    runtime: ToolRuntime[RuntimeContext],
    description: str = "",
    project: str = "",
    priority: str = "medium",
    due_at: datetime | None = None,
    planned_start_at: datetime | None = None,
    planned_end_at: datetime | None = None,
    estimated_minutes: int | None = None,
    tags: list[str] | None = None,
) -> dict[str, object]:
    """Create a task for the current user. This does not complete or delete existing work."""

    task = TaskService.create_task(
        CreateTaskCommand(
            user=require_writable(runtime),
            title=title,
            description=description,
            project=project,
            priority=priority,
            due_at=due_at,
            planned_start_at=planned_start_at,
            planned_end_at=planned_end_at,
            estimated_minutes=estimated_minutes,
            tags=tags or [],
            source="agent",
            origin="agent",
        )
    )
    return model_dict(task, TASK_FIELDS)


@tool
def create_task_batch(
    tasks: list[TaskDraftInput],
    runtime: ToolRuntime[RuntimeContext],
) -> list[dict[str, object]]:
    """Create several tasks atomically; the batch receives one approval before any write."""

    actor = require_writable(runtime)
    commands = [
        CreateTaskCommand(
            user=actor,
            title=item.title,
            description=item.description,
            project=item.project,
            priority=item.priority,
            due_at=item.due_at,
            planned_start_at=item.planned_start_at,
            planned_end_at=item.planned_end_at,
            estimated_minutes=item.estimated_minutes,
            tags=item.tags,
                source="agent",
                origin="agent",
        )
        for item in tasks
    ]
    created = TaskService.create_tasks(commands=commands)
    return [model_dict(task, TASK_FIELDS) for task in created]


@tool
def update_task(
    task_id: UUID,
    expected_version: int,
    runtime: ToolRuntime[RuntimeContext],
    title: str | None = None,
    description: str | None = None,
    project: str | None = None,
    priority: str | None = None,
    due_at: datetime | None = None,
    estimated_minutes: int | None = None,
    tags: list[str] | None = None,
) -> dict[str, object]:
    """Update task details without silently changing its lifecycle state."""

    changes = {
        key: value
        for key, value in {
            "title": title,
            "description": description,
            "project": project,
            "priority": priority,
            "due_at": due_at,
            "estimated_minutes": estimated_minutes,
            "tags": tags,
        }.items()
        if value is not None
    }
    if not changes:
        raise ValueError("Provide at least one task field to update")
    task = TaskService.update_task(
        UpdateTaskCommand(
            user=require_writable(runtime),
            task_id=task_id,
            expected_version=expected_version,
            changes=changes,
            origin="agent",
        )
    )
    return model_dict(task, TASK_FIELDS)


@tool
def change_task_state(
    task_id: UUID,
    status: str,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Move a task through its state machine: in_progress, completed, or cancelled."""

    task = TaskService.change_task_state(
        task_id=task_id,
        user=require_writable(runtime),
        status=status,
        occurred_at=runtime.context.current_datetime,
        origin="agent",
    )
    return model_dict(task, TASK_FIELDS)


@tool
def change_task_batch_state(
    items: list[dict[str, object]],
    status: str,
    runtime: ToolRuntime[RuntimeContext],
) -> list[dict[str, object]]:
    """Complete or cancel a versioned group of tasks atomically after one approval."""

    parsed: list[tuple[UUID, int]] = []
    for item in items:
        try:
            raw_version = item["expected_version"]
            if not isinstance(raw_version, int | str):
                raise TypeError
            parsed.append((UUID(str(item["task_id"])), int(raw_version)))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Each item needs task_id and expected_version") from exc
    tasks = TaskService.change_tasks_state(
        user=require_writable(runtime),
        items=parsed,
        status=status,
        occurred_at=runtime.context.current_datetime,
        origin="agent",
    )
    return [model_dict(task, TASK_FIELDS) for task in tasks]


@tool
def complete_task(task_id: UUID, runtime: ToolRuntime[RuntimeContext]) -> dict[str, object]:
    """Mark one task owned by the current user as completed."""

    signal = TaskExecutionSignalService.record(
        RecordExecutionSignalCommand(
            task_id=task_id,
            user=require_writable(runtime),
            signal_type="completed",
            occurred_at=runtime.context.current_datetime,
            idempotency_key=f"agent-complete:{runtime.context.request_id}:{task_id}",
            source="agent",
        )
    )
    task = signal.task
    task.refresh_from_db()
    return model_dict(task, TASK_FIELDS)


@tool
def cancel_task(task_id: UUID, runtime: ToolRuntime[RuntimeContext]) -> dict[str, object]:
    """Cancel one identified active task without deleting its history."""

    task = TaskService.cancel_task(
        task_id=task_id,
        user=require_writable(runtime),
        occurred_at=runtime.context.current_datetime,
        origin="agent",
    )
    return model_dict(task, TASK_FIELDS)


@tool
def reschedule_task(
    task_id: UUID,
    planned_start_at: datetime,
    planned_end_at: datetime,
    runtime: ToolRuntime[RuntimeContext],
) -> dict[str, object]:
    """Set a task's planned time range without changing calendar events."""

    task = TaskService.reschedule_task(
        task_id=task_id,
        user=require_writable(runtime),
        planned_start_at=planned_start_at,
        planned_end_at=planned_end_at,
        origin="agent",
    )
    return model_dict(task, TASK_FIELDS)


TASK_READ_TOOLS = [list_tasks, get_task, get_task_execution_summary]
TASK_WRITE_TOOLS = [
    create_task,
    create_task_batch,
    update_task,
    change_task_state,
    change_task_batch_state,
    complete_task,
    reschedule_task,
    cancel_task,
]
TASK_TOOLS = [*TASK_READ_TOOLS, *TASK_WRITE_TOOLS]
