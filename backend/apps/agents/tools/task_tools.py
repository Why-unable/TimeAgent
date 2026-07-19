from datetime import datetime
from uuid import UUID

from langchain.tools import ToolRuntime, tool

from apps.agents.context import RuntimeContext
from apps.agents.tools.common import model_dict, require_actor, require_writable
from apps.tasks.services import CreateTaskCommand, TaskQuery, TaskService

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
)


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
def create_task(
    title: str,
    runtime: ToolRuntime[RuntimeContext],
    description: str = "",
    project: str = "",
    priority: str = "medium",
    due_at: datetime | None = None,
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
            estimated_minutes=estimated_minutes,
            tags=tags or [],
            source="agent",
        )
    )
    return model_dict(task, TASK_FIELDS)


@tool
def complete_task(task_id: UUID, runtime: ToolRuntime[RuntimeContext]) -> dict[str, object]:
    """Mark one task owned by the current user as completed."""

    task = TaskService.complete_task(
        task_id=task_id,
        user=require_writable(runtime),
        occurred_at=runtime.context.current_datetime,
    )
    return model_dict(task, TASK_FIELDS)


@tool
def cancel_task(task_id: UUID, runtime: ToolRuntime[RuntimeContext]) -> dict[str, object]:
    """Cancel one identified active task without deleting its history."""

    task = TaskService.cancel_task(
        task_id=task_id,
        user=require_writable(runtime),
        occurred_at=runtime.context.current_datetime,
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
    )
    return model_dict(task, TASK_FIELDS)


TASK_TOOLS = [
    list_tasks,
    get_task,
    create_task,
    complete_task,
    reschedule_task,
    cancel_task,
]
