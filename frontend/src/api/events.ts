import type { components } from "./generated/schema";
import { apiRequest } from "./client";

export type CalendarEvent = components["schemas"]["CalendarEvent"];
export type CreateCalendarEvent = components["schemas"]["CreateCalendarEvent"];
export type UpdateCalendarEvent = components["schemas"]["PatchedUpdateCalendarEvent"];

export interface EventListParams {
  startsBefore?: string;
  endsAfter?: string;
  statuses?: NonNullable<CalendarEvent["status"]>[];
}

export function listEvents(params: EventListParams = {}) {
  const query = new URLSearchParams();
  if (params.startsBefore) query.set("starts_before", params.startsBefore);
  if (params.endsAfter) query.set("ends_after", params.endsAfter);
  params.statuses?.forEach((status) => query.append("status", status));
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return apiRequest<CalendarEvent[]>(`/api/v1/events/${suffix}`);
}

export function createEvent(input: CreateCalendarEvent) {
  return apiRequest<CalendarEvent>("/api/v1/events/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateEvent(
  eventId: string,
  expectedVersion: number,
  input: UpdateCalendarEvent,
) {
  return apiRequest<CalendarEvent>(
    `/api/v1/events/${eventId}/?expected_version=${expectedVersion}`,
    {
      method: "PATCH",
      body: JSON.stringify(input),
    },
  );
}

export function cancelEvent(eventId: string, expectedVersion: number) {
  return apiRequest<void>(
    `/api/v1/events/${eventId}/?expected_version=${expectedVersion}`,
    { method: "DELETE" },
  );
}
