import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { completeTask } from "../../api/tasks";
import { getTodaySummary } from "../../api/today";
import { taskQueryKey } from "../tasks/hooks";

export const todayQueryKey = ["today"] as const;

export function useTodaySummary() {
  return useQuery({
    queryKey: todayQueryKey,
    queryFn: getTodaySummary,
    retry: false,
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
