import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { completeTask } from "../../api/tasks";
import { getTodaySummary } from "../../api/today";
import { taskQueryKey } from "../tasks/hooks";
import type { TodaySummary } from "../../api/today";

export const todayQueryKey = ["today"] as const;

/** Schedule a refresh at the next server-defined bucket boundary. The server
 * remains responsible for classifying items; the client only refreshes data. */
export function nextTodayRefreshDelay(summary: TodaySummary, now = Date.now()): number {
  const boundaries: Array<string | null | undefined> = [summary.day_end_at];
  for (const item of [
    ...summary.execution_now,
    ...summary.execution_next,
    ...summary.execution_later,
  ]) {
    boundaries.push(item.start_at, item.end_at, item.due_at);
  }

  const nextBoundary = boundaries
    .filter((value): value is string => Boolean(value))
    .map((value) => Date.parse(value))
    .filter((timestamp) => Number.isFinite(timestamp) && timestamp > now)
    .sort((left, right) => left - right)[0];

  const refreshAtBoundary = nextBoundary === undefined
    ? 5 * 60_000
    : Math.max(1_000, nextBoundary - now + 1_000);
  return Math.min(refreshAtBoundary, 5 * 60_000);
}

export function useTodaySummary() {
  return useQuery({
    queryKey: todayQueryKey,
    queryFn: getTodaySummary,
    retry: false,
    refetchInterval: (query) => query.state.data
      ? nextTodayRefreshDelay(query.state.data)
      : false,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  });
}

export function useCompleteTodayTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: completeTask,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: todayQueryKey }),
        queryClient.invalidateQueries({ queryKey: taskQueryKey }),
      ]);
    },
  });
}
