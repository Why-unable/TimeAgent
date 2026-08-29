import type { components } from "./generated/schema";
import { apiRequest } from "./client";

export type Task = components["schemas"]["Task"];
export type CreateTask = components["schemas"]["CreateTask"];
export type UpdateTask = components["schemas"]["PatchedUpdateTask"];
export type CreateTaskExecutionSignal = components["schemas"]["CreateTaskExecutionSignal"];
export type TaskExecutionSignal = components["schemas"]["TaskExecutionSignal"];
export type TaskExecutionSummary = components["schemas"]["TaskExecutionSummary"];

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

function createIdempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `execution-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function recordTaskExecutionSignal(
  taskId: string,
  signalType: CreateTaskExecutionSignal["signal_type"],
  options: Pick<CreateTaskExecutionSignal, "occurred_at" | "idempotency_key"> = {
    occurred_at: new Date().toISOString(),
    idempotency_key: createIdempotencyKey(),
  },
) {
  const input: CreateTaskExecutionSignal = {
    signal_type: signalType,
    occurred_at: options.occurred_at,
    idempotency_key: options.idempotency_key,
    source: "web",
  };
  return apiRequest<TaskExecutionSignal>(`/api/v1/tasks/${taskId}/execution-signals/`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getTaskExecutionSummary(taskId: string) {
  return apiRequest<TaskExecutionSummary>(`/api/v1/tasks/${taskId}/execution-summary/`);
}
