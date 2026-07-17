import type { components } from "./generated/schema";
import { apiRequest } from "./client";

export type Reminder = components["schemas"]["Reminder"];
export type CreateReminder = components["schemas"]["CreateReminder"];

export function listReminders() {
  return apiRequest<Reminder[]>("/api/v1/reminders/");
}

export function createReminder(input: CreateReminder) {
  return apiRequest<Reminder>("/api/v1/reminders/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function cancelReminder(reminderId: string) {
  return apiRequest<void>(`/api/v1/reminders/${reminderId}/`, {
    method: "DELETE",
  });
}
