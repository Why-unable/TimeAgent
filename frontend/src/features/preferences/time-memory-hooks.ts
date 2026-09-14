import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  clearCurrentTimeMemory,
  forgetTimeMemoryPattern,
  forgetTimeMemoryPlace,
  getCapacityForecast,
  getCurrentTimeMemory,
  getDecisionProfile,
  getDurationRecommendation,
  getMemoryProposals,
  getRecentMemoryProposals,
  getSemanticMemories,
  decideMemoryProposal,
  recordDecisionFeedback,
  undoMemoryProposal,
} from "../../api/time-memory";

export const timeMemoryQueryKey = ["time-memory"] as const;
export const decisionProfileQueryKey = ["time-memory", "decision-profile"] as const;
export const durationRecommendationQueryKey = [
  "time-memory",
  "duration-recommendation",
] as const;
export const capacityForecastQueryKey = ["time-memory", "capacity-forecast"] as const;
export const semanticMemoryQueryKey = ["time-memory", "semantic"] as const;
export const memoryProposalQueryKey = ["time-memory", "proposals"] as const;
export const recentMemoryProposalQueryKey = ["time-memory", "proposals", "recent"] as const;

export function useCurrentTimeMemory() {
  return useQuery({
    queryKey: timeMemoryQueryKey,
    queryFn: getCurrentTimeMemory,
    retry: false,
  });
}

export function useDecisionProfile() {
  return useQuery({
    queryKey: decisionProfileQueryKey,
    queryFn: getDecisionProfile,
    retry: false,
  });
}

export function useDurationRecommendation(taskId: string | undefined) {
  return useQuery({
    queryKey: [...durationRecommendationQueryKey, taskId],
    queryFn: () => getDurationRecommendation(taskId as string),
    enabled: Boolean(taskId),
    retry: false,
  });
}

export function useCapacityForecast(
  input: { range_start: string; range_end: string } | undefined,
) {
  return useQuery({
    queryKey: [...capacityForecastQueryKey, input],
    queryFn: () => getCapacityForecast(input as { range_start: string; range_end: string }),
    enabled: Boolean(input),
    retry: false,
  });
}

export function useSemanticMemories() {
  return useQuery({
    queryKey: semanticMemoryQueryKey,
    queryFn: getSemanticMemories,
    retry: false,
  });
}

export function useMemoryProposals() {
  return useQuery({
    queryKey: memoryProposalQueryKey,
    queryFn: getMemoryProposals,
    retry: false,
  });
}

export function useRecentMemoryProposals() {
  return useQuery({
    queryKey: recentMemoryProposalQueryKey,
    queryFn: getRecentMemoryProposals,
    retry: false,
  });
}

export function useDecideMemoryProposal() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ proposalId, approve }: { proposalId: string; approve: boolean }) =>
      decideMemoryProposal(proposalId, approve),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: memoryProposalQueryKey }),
        client.invalidateQueries({ queryKey: semanticMemoryQueryKey }),
      ]);
    },
  });
}

export function useUndoMemoryProposal() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: undoMemoryProposal,
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: recentMemoryProposalQueryKey }),
        client.invalidateQueries({ queryKey: memoryProposalQueryKey }),
        client.invalidateQueries({ queryKey: semanticMemoryQueryKey }),
      ]);
    },
  });
}

export function useRecordDecisionFeedback() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: recordDecisionFeedback,
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: decisionProfileQueryKey }),
        client.invalidateQueries({ queryKey: durationRecommendationQueryKey }),
      ]);
    },
  });
}

export function useClearCurrentTimeMemory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: clearCurrentTimeMemory,
    onSuccess: () => client.invalidateQueries({ queryKey: timeMemoryQueryKey }),
  });
}

export function useForgetTimeMemoryPlace() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: forgetTimeMemoryPlace,
    onSuccess: () => client.invalidateQueries({ queryKey: timeMemoryQueryKey }),
  });
}

export function useForgetTimeMemoryPattern() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: forgetTimeMemoryPattern,
    onSuccess: () => client.invalidateQueries({ queryKey: timeMemoryQueryKey }),
  });
}
