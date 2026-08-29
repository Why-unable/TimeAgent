import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createBriefingDefinition,
  launchBriefing,
  listBriefingDefinitions,
  listBriefingRuns,
  getEveningBriefingPreview,
  updateBriefingDefinition,
} from "../../api/briefings";
import type { BriefingDefinition } from "../../api/briefings";

export const briefingKeys = {
  definitions: ["briefings", "definitions"] as const,
  runs: ["briefings", "runs"] as const,
};

export function useBriefingDefinitions() {
  return useQuery({ queryKey: briefingKeys.definitions, queryFn: listBriefingDefinitions });
}

export function useBriefingRuns() {
  return useQuery({ queryKey: briefingKeys.runs, queryFn: listBriefingRuns });
}

export function useEveningBriefingPreview() {
  return useQuery({
    queryKey: ["briefings", "evening-preview"],
    queryFn: getEveningBriefingPreview,
    retry: false,
  });
}

export function useCreateBriefingDefinition() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: createBriefingDefinition,
    onSuccess: () => client.invalidateQueries({ queryKey: briefingKeys.definitions }),
  });
}

export function useUpdateBriefingDefinition() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: {
      id: string;
      input: Partial<Pick<BriefingDefinition, "name" | "enabled_sections" | "style" | "include_empty_sections" | "locale" | "timezone" | "is_active">>;
    }) =>
      updateBriefingDefinition(id, input),
    onSuccess: () => client.invalidateQueries({ queryKey: briefingKeys.definitions }),
  });
}

export function useLaunchBriefing() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ definitionId, targetDate }: { definitionId: string | null; targetDate: string }) =>
      launchBriefing(definitionId, targetDate),
    onSuccess: () => client.invalidateQueries({ queryKey: briefingKeys.runs }),
  });
}
