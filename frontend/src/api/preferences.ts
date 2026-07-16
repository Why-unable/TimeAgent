import type { components } from "./generated/schema";
import { apiRequest } from "./client";

export type UserPreference = components["schemas"]["UserPreference"];
export type UserPreferenceUpdate = components["schemas"]["PatchedUserPreference"];

export function getCurrentUserPreference() {
  return apiRequest<UserPreference>("/api/v1/preferences/me/");
}

export function updateCurrentUserPreference(changes: UserPreferenceUpdate) {
  return apiRequest<UserPreference>("/api/v1/preferences/me/", {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

