import type { components } from "./generated/schema";
import { apiRequest } from "./client";

export type TimeMemoryStatus = components["schemas"]["TimeMemoryStatus"];
export type DecisionProfile = components["schemas"]["DecisionProfile"];
export type DecisionFeedback = components["schemas"]["DecisionFeedback"];
export type DurationRecommendation = components["schemas"]["DurationRecommendation"];
export type CapacityForecast = components["schemas"]["CapacityForecast"];

export type TimeMemoryProfile = {
  schema_version: number;
  user_id: string;
  generated_at: string;
  data_until: string;
  timezone: string;
  common_places: CommonPlace[];
  behavior_windows: Partial<Record<WindowName, BehaviorWindow>>;
  stable_patterns: StablePattern[];
  profile_summary: string;
  version: number;
};

export type WindowName = "7d" | "30d" | "180d";

export type CommonPlace = {
  place_id: string;
  name: string;
  normalized_name: string;
  event_count: number;
  total_scheduled_hours: number;
  typical_weekdays: number[];
  typical_time_ranges: string[];
  first_seen_at: string | null;
  last_seen_at: string | null;
  confidence: number;
  score: number;
};

export type BehaviorWindow = {
  window: WindowName;
  start_date: string;
  end_date: string;
  sample_days: number;
  event_count: number;
  task_count: number;
  reminder_count: number;
  completed_task_count: number;
  cancelled_task_count: number;
  source_distribution: Record<string, number>;
  schedule_pattern: SchedulePattern;
  planning_pattern: PlanningPattern;
  change_pattern: ChangePattern;
  adaptive_planning_pattern?: AdaptivePlanningPattern;
  summary: string;
  confidence: number;
};

export type SchedulePattern = {
  total_scheduled_hours: number;
  average_daily_scheduled_hours: number;
  median_daily_scheduled_hours: number;
  scheduled_day_count: number;
  busy_day_count: number;
  light_day_count: number;
  rest_day_count: number;
  consecutive_busy_days_max: number;
  weekday_average_hours: number;
  weekend_average_hours: number;
  peak_time_ranges: string[];
  work_rest_balance: string;
  summary: string;
};

export type PlanningPattern = {
  created_event_count: number;
  creation_session_count: number;
  batch_creation_session_count: number;
  batch_creation_ratio: number;
  incremental_creation_ratio: number;
  average_lead_time_hours: number;
  median_lead_time_hours: number;
  last_minute_creation_ratio: number;
  long_horizon_creation_ratio: number;
  typical_creation_time_ranges: string[];
  planning_style: string;
  summary: string;
};

export type ChangePattern = {
  modified_event_count: number;
  rescheduled_event_count: number;
  postponed_event_count: number;
  advanced_event_count: number;
  cancelled_event_count: number;
  completed_event_count: number;
  reschedule_ratio: number;
  postpone_ratio: number;
  cancellation_ratio: number;
  completion_ratio: number | null;
  average_reschedule_delta_hours: number;
  dominant_change_behavior: string;
  summary: string;
};

export type AdaptivePlanningPattern = {
  automated_move_count: number;
  reverted_move_count: number;
  user_modified_after_move_count: number;
  accepted_move_count: number;
  median_move_minutes: number;
  revert_or_modify_ratio: number;
  confidence: number;
  summary: string;
};

export type StablePattern = {
  pattern_id: string;
  pattern_type: string;
  summary: string;
  evidence_windows: WindowName[];
  confidence: number;
  first_detected_at: string;
  last_confirmed_at: string;
  unsupported_rebuild_count: number;
  status: "active" | "weakening" | "expired";
  score: number;
};

export function getCurrentTimeMemory() {
  return apiRequest<TimeMemoryStatus>("/api/v1/time-memory/me/");
}

export function getDecisionProfile() {
  return apiRequest<DecisionProfile>("/api/v1/time-memory/me/decision-profile/");
}

export function recordDecisionFeedback(input: DecisionFeedback) {
  return apiRequest<{ id: string }>("/api/v1/time-memory/me/decision-profile/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getDurationRecommendation(taskId: string) {
  return apiRequest<DurationRecommendation>(
    `/api/v1/time-memory/me/duration-recommendations/${encodeURIComponent(taskId)}/`,
  );
}

export function getCapacityForecast(input: { range_start: string; range_end: string }) {
  const query = new URLSearchParams(input);
  return apiRequest<CapacityForecast>(
    `/api/v1/time-memory/me/capacity-forecast/?${query.toString()}`,
  );
}

export function clearCurrentTimeMemory() {
  return apiRequest<void>("/api/v1/time-memory/me/", { method: "DELETE" });
}

export function forgetTimeMemoryPlace(placeId: string) {
  return apiRequest<void>(`/api/v1/time-memory/me/places/${encodeURIComponent(placeId)}/`, {
    method: "DELETE",
  });
}

export function forgetTimeMemoryPattern(patternId: string) {
  return apiRequest<void>(
    `/api/v1/time-memory/me/patterns/${encodeURIComponent(patternId)}/`,
    { method: "DELETE" },
  );
}

export function parseTimeMemoryProfile(value: unknown): TimeMemoryProfile | null {
  if (!value || typeof value !== "object") return null;
  return value as TimeMemoryProfile;
}
