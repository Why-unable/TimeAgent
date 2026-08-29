import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  actOnTemporalInsight,
  getTemporalInsight,
  listTemporalInsights,
  type TemporalInsightAction,
} from "../../api/insights";

export const insightQueryKey = ["temporal-insights"] as const;

export function useTemporalInsights() {
  return useQuery({ queryKey: insightQueryKey, queryFn: listTemporalInsights, retry: false });
}

export function useTemporalInsight(insightId: string | undefined) {
  return useQuery({
    queryKey: [...insightQueryKey, insightId],
    queryFn: () => getTemporalInsight(insightId ?? ""),
    enabled: Boolean(insightId),
    retry: false,
  });
}

export function useActOnTemporalInsight() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ insightId, input }: { insightId: string; input: TemporalInsightAction }) =>
      actOnTemporalInsight(insightId, input),
    onSuccess: () => client.invalidateQueries({ queryKey: insightQueryKey }),
  });
}
