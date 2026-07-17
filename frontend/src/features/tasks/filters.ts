import type { Task } from "../../api/tasks";
import { getLocalDateKey } from "../../utils/datetime";

export type TaskFilter =
  | "inbox"
  | "today"
  | "upcoming"
  | "overdue"
  | "planned"
  | "in_progress"
  | "completed"
  | "all";

function isActive(task: Task) {
  return task.status !== "completed" && task.status !== "cancelled";
}

export function filterTasks(tasks: Task[], filter: TaskFilter, timezone: string, now = new Date()) {
  const today = getLocalDateKey(now, timezone);
  return tasks.filter((task) => {
    const dueDate = task.due_at ? getLocalDateKey(task.due_at, timezone) : undefined;
    const plannedDate = task.planned_start_at
      ? getLocalDateKey(task.planned_start_at, timezone)
      : undefined;
    switch (filter) {
      case "inbox":
        return task.status === "pending" && !task.planned_start_at;
      case "today":
        return isActive(task) && (dueDate === today || plannedDate === today);
      case "upcoming":
        return isActive(task) && dueDate !== undefined && dueDate > today;
      case "overdue":
        return isActive(task) && dueDate !== undefined && dueDate < today;
      case "planned":
        return isActive(task) && Boolean(task.planned_start_at);
      case "in_progress":
        return task.status === "in_progress";
      case "completed":
        return task.status === "completed";
      default:
        return true;
    }
  });
}
