import type { components } from "./generated/schema";
import { apiRequest } from "./client";

export type TemporalInsight = components["schemas"]["TemporalInsight"];
export type TemporalInsightAction = components["schemas"]["TemporalInsightAction"];

export function listTemporalInsights() {
  return apiRequest<TemporalInsight[]>("/api/v1/insights/");
}

export function getTemporalInsight(insightId: string) {
  return apiRequest<TemporalInsight>(`/api/v1/insights/${insightId}/`);
}

export function actOnTemporalInsight(insightId: string, input: TemporalInsightAction) {
  return apiRequest<TemporalInsight>(`/api/v1/insights/${insightId}/action/`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
