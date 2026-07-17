import type { components } from "./generated/schema";
import { apiRequest } from "./client";

export type TodaySummary = components["schemas"]["TodaySummary"];
export type ScheduleConflict = components["schemas"]["ScheduleConflict"];

export function getTodaySummary() {
  return apiRequest<TodaySummary>("/api/v1/today/");
}
