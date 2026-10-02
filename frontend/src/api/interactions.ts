import { apiRequest } from "./client";
import type { components } from "./generated/schema";

export type InteractionType = components["schemas"]["InteractionTypeEnum"];
export type InteractionStatus = components["schemas"]["InteractionStatusEnum"];
export type EnsureInteractionInput = components["schemas"]["EnsureInteraction"];
export type InteractionSubmitInput = components["schemas"]["InteractionSubmit"];
export type InteractionArtifact = Omit<
  components["schemas"]["InteractionArtifact"],
  "payload" | "allowed_actions" | "version" | "expires_at"
> & {
  payload: Record<string, unknown>;
  allowed_actions: string[];
  version: number;
  expires_at: string;
};
export type InteractionSubmitResponse = Omit<
  components["schemas"]["InteractionSubmissionResponse"],
  "interaction" | "conflicts" | "candidate"
> & {
  interaction: InteractionArtifact;
  conflicts: Array<{ kind: string; label: string; start_at: string; end_at: string }>;
  candidate: { start_at: string; end_at: string } | null;
};
export type InteractionTelemetryInput = Pick<
  components["schemas"]["InteractionTelemetry"],
  "event_type" | "interaction_type"
> & Partial<Omit<components["schemas"]["InteractionTelemetry"], "event_type" | "interaction_type">>;

export function ensureInteraction(input: EnsureInteractionInput) {
  return apiRequest<InteractionArtifact>("/api/v1/interactions/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listPendingInteractions(input: {
  type?: InteractionType;
  plan_id?: string;
  task_id?: string;
} = {}) {
  const query = new URLSearchParams();
  if (input.type) query.set("type", input.type);
  if (input.plan_id) query.set("plan_id", input.plan_id);
  if (input.task_id) query.set("task_id", input.task_id);
  const suffix = query.size ? `?${query.toString()}` : "";
  return apiRequest<InteractionArtifact[]>(`/api/v1/interactions/${suffix}`);
}

export function submitInteraction(
  interactionId: string,
  input: InteractionSubmitInput,
) {
  return apiRequest<InteractionSubmitResponse>(
    `/api/v1/interactions/${interactionId}/submit/`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function recordInteractionTelemetry(input: InteractionTelemetryInput) {
  return apiRequest<void>("/api/v1/interactions/telemetry/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
