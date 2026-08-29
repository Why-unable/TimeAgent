import type { components } from "./generated/schema";
import { apiRequest } from "./client";

export type FreeTimeRecommendation = components["schemas"]["FreeTimeRecommendation"];
export type SchedulePlan = components["schemas"]["SchedulePlan"];
export type SchedulePlanCreate = components["schemas"]["SchedulePlanCreate"];
export type SchedulePlanApply = components["schemas"]["SchedulePlanApply"];
export type SchedulePlanCompare = components["schemas"]["SchedulePlanCompare"];
export type SchedulePlanComparison = components["schemas"]["SchedulePlanComparison"];
export type SchedulePlanRegenerate = components["schemas"]["SchedulePlanRegenerate"];
export type SchedulePlanEdit = components["schemas"]["SchedulePlanEdit"];
export type SchedulePlanValidation = components["schemas"]["SchedulePlanValidation"];
export type SchedulePlanValidationResult = components["schemas"]["SchedulePlanValidationResult"];
export type LocalReplanPreview = components["schemas"]["LocalReplanPreview"];
export type LocalReplanPreviewRequest = components["schemas"]["LocalReplanPreviewRequest"];
export type LocalReplanApplyRequest = components["schemas"]["LocalReplanApplyRequest"];
export type AutomationPolicy = components["schemas"]["AutomationPolicy"];
export type AutomationPolicyWrite = components["schemas"]["AutomationPolicyWrite"];
export type ScheduleChangeBatch = components["schemas"]["ScheduleChangeBatch"];

export type ScheduleDisruption = {
  task_id: string;
  task_title: string;
  task_version: number;
  event_id: string;
  event_title: string;
  blocked_start: string;
  blocked_end: string;
  overlap_minutes: number;
  reason_codes: string[];
};

export function getFreeTimeRecommendations(input: {
  range_start: string;
  range_end: string;
  duration_minutes: number;
  max_results?: number;
}) {
  const query = new URLSearchParams({
    range_start: input.range_start,
    range_end: input.range_end,
    duration_minutes: String(input.duration_minutes),
    max_results: String(input.max_results ?? 8),
  });
  return apiRequest<FreeTimeRecommendation>(`/api/v1/planning/free-time-recommendations/?${query.toString()}`);
}

export function createSchedulePlan(input: SchedulePlanCreate) {
  return apiRequest<SchedulePlan>("/api/v1/planning/plans/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function applySchedulePlan(planId: string, input: SchedulePlanApply) {
  return apiRequest<SchedulePlan>(`/api/v1/planning/plans/${planId}/apply/`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function compareSchedulePlans(input: SchedulePlanCompare) {
  return apiRequest<SchedulePlanComparison>("/api/v1/planning/plans/compare/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function regenerateSchedulePlan(planId: string, input: SchedulePlanRegenerate) {
  return apiRequest<SchedulePlan>(`/api/v1/planning/plans/${planId}/regenerate/`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function editSchedulePlan(planId: string, input: SchedulePlanEdit) {
  return apiRequest<SchedulePlan>(`/api/v1/planning/plans/${planId}/edit/`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function validateSchedulePlan(planId: string, input: SchedulePlanValidation) {
  return apiRequest<SchedulePlanValidationResult>(`/api/v1/planning/plans/${planId}/validate/`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function abandonSchedulePlan(planId: string, input: SchedulePlanApply) {
  return apiRequest<SchedulePlan>(`/api/v1/planning/plans/${planId}/abandon/`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function previewLocalReplan(input: LocalReplanPreviewRequest) {
  return apiRequest<LocalReplanPreview>("/api/v1/planning/plans/local-replan-preview/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function applyLocalReplan(input: LocalReplanApplyRequest) {
  return apiRequest<ScheduleChangeBatch>("/api/v1/planning/plans/local-replan-apply/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function revertScheduleChangeBatch(batchId: string) {
  return apiRequest<ScheduleChangeBatch>(`/api/v1/planning/change-batches/${batchId}/revert/`, {
    method: "POST",
  });
}

export function listAutomationPolicies() {
  return apiRequest<AutomationPolicy[]>("/api/v1/planning/automation-policies/");
}

export function saveAutomationPolicy(input: AutomationPolicyWrite) {
  return apiRequest<AutomationPolicy>("/api/v1/planning/automation-policies/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateAutomationPolicy(policyId: string, input: Partial<AutomationPolicyWrite>) {
  return apiRequest<AutomationPolicy>(`/api/v1/planning/automation-policies/${policyId}/`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function detectScheduleDisruptions(input: { range_start: string; range_end: string }) {
  return apiRequest<ScheduleDisruption[]>("/api/v1/planning/disruptions/detect/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
