import { apiRequest } from "./client";
import type { AgentRun, Conversation } from "./chat";

export type BriefingSectionKey = "calendar" | "tasks";
export type BriefingStyle = "concise" | "balanced" | "detailed";
export type BriefingRunStatus = "pending" | "running" | "completed" | "partial" | "failed";

export interface BriefingDefinition {
  id: string;
  name: string;
  enabled_sections: BriefingSectionKey[];
  locale: string;
  timezone: string;
  style: BriefingStyle;
  include_empty_sections: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
export interface BriefingSourceReference {
  kind: "calendar_event" | "task";
  id: string;
  title: string;
  occurred_at: string | null;
}

export interface BriefingSectionRun {
  id: string;
  section_key: string;
  status: "pending" | "running" | "completed" | "failed";
  source_snapshot: Record<string, unknown>;
  source_references: BriefingSourceReference[];
  warning: string;
  error_code: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface BriefingRun {
  id: string;
  definition_id: string;
  conversation_id: string | null;
  agent_run_id: string | null;
  operation_id: string;
  trigger_type: string;
  target_date: string;
  timezone: string;
  status: BriefingRunStatus;
  definition_snapshot: Record<string, unknown>;
  structured_result: Record<string, unknown>;
  rendered_markdown: string;
  warnings: string[];
  failure_code: string;
  failure_message: string;
  created_at: string;
  completed_at: string | null;
  section_runs: BriefingSectionRun[];
}

export interface BriefingLaunchResponse {
  conversation: Conversation;
  agent_run: AgentRun;
}

export function listBriefingDefinitions() {
  return apiRequest<BriefingDefinition[]>("/api/v1/briefings/definitions/");
}

export function createBriefingDefinition(
  input: Pick<BriefingDefinition, "name" | "enabled_sections" | "style" | "include_empty_sections">
    & Partial<Pick<BriefingDefinition, "locale" | "timezone">>,
) {
  return apiRequest<BriefingDefinition>("/api/v1/briefings/definitions/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateBriefingDefinition(
  id: string,
  input: Partial<Pick<BriefingDefinition, "name" | "enabled_sections" | "style" | "include_empty_sections" | "locale" | "timezone" | "is_active">>,
) {
  return apiRequest<BriefingDefinition>(`/api/v1/briefings/definitions/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function listBriefingRuns() {
  return apiRequest<BriefingRun[]>("/api/v1/briefings/runs/");
}

export function launchBriefing(definitionId: string | null, targetDate: string) {
  return apiRequest<BriefingLaunchResponse>("/api/v1/briefings/runs/", {
    method: "POST",
    body: JSON.stringify({
      definition_id: definitionId,
      target_date: targetDate,
      operation_id: crypto.randomUUID(),
    }),
  });
}
