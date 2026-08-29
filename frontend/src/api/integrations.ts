import type { components } from "./generated/schema";
import { apiRequest } from "./client";

export type CalendarSyncConnection = components["schemas"]["CalendarSyncConnection"];
export type CalendarOAuthStartResult = components["schemas"]["CalendarOAuthStartResult"];

export function listCalendarSyncConnections() {
  return apiRequest<CalendarSyncConnection[]>(
    "/api/v1/integrations/calendar/connections/",
  );
}

export function createCalendarSyncConnection(input: {
  provider_name: string;
  account_reference: string;
  calendar_id: string;
  calendar_name: string;
  timezone: string;
  enabled?: boolean;
}) {
  return apiRequest<CalendarSyncConnection>(
    "/api/v1/integrations/calendar/connections/",
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function syncCalendarConnection(
  connectionId: string,
  input: { starts_at_or_after: string; starts_before: string },
) {
  return apiRequest<{
    connection_id: string;
    fetched_count: number;
    created_count: number;
    updated_count: number;
    cancelled_count: number;
    synced_at: string;
  }>(`/api/v1/integrations/calendar/connections/${connectionId}/sync/`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function startGoogleCalendarOAuth() {
  return apiRequest<CalendarOAuthStartResult>(
    "/api/v1/integrations/calendar/oauth/google/start/",
    { method: "POST" },
  );
}

export function disconnectGoogleCalendar(connectionId: string) {
  return apiRequest<void>(
    `/api/v1/integrations/calendar/connections/${connectionId}/disconnect/`,
    { method: "DELETE" },
  );
}
