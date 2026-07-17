import type { components } from "./generated/schema";
import { apiRequest } from "./client";

export type Task = components["schemas"]["Task"];
export type CreateTask = components["schemas"]["CreateTask"];
export type UpdateTask = components["schemas"]["PatchedUpdateTask"];

export function getTaskTags(task: Task): string[] {
  return Array.isArray(task.tags)
    ? task.tags.filter((tag): tag is string => typeof tag === "string")
    : [];
}

export interface TaskListParams {
  statuses?: NonNullable<Task["status"]>[];
  dueBefore?: string;
  plannedStartsBefore?: string;
  plannedEndsAfter?: string;
}

export function listTasks(params: TaskListParams = {}) {
  const query = new URLSearchParams();
  params.statuses?.forEach((status) => query.append("status", status));
  if (params.dueBefore) query.set("due_before", params.dueBefore);
  if (params.plannedStartsBefore) {
    query.set("planned_starts_before", params.plannedStartsBefore);
  }
  if (params.plannedEndsAfter) query.set("planned_ends_after", params.plannedEndsAfter);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return apiRequest<Task[]>(`/api/v1/tasks/${suffix}`);
}

export function createTask(input: CreateTask) {
  return apiRequest<Task>("/api/v1/tasks/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateTask(taskId: string, input: UpdateTask) {
  return apiRequest<Task>(`/api/v1/tasks/${taskId}/`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function completeTask(taskId: string) {
  return apiRequest<Task>(`/api/v1/tasks/${taskId}/complete/`, { method: "POST" });
}
