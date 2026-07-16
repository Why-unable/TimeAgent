import { apiRequest } from "./client";
import type { components } from "./generated/schema";

export type ReadinessResponse = components["schemas"]["ReadyResponse"];

export function getReadiness() {
  return apiRequest<ReadinessResponse>("/health/ready");
}
