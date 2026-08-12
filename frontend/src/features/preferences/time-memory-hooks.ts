import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  clearCurrentTimeMemory,
  forgetTimeMemoryPattern,
  forgetTimeMemoryPlace,
  getCurrentTimeMemory,
} from "../../api/time-memory";

export const timeMemoryQueryKey = ["time-memory"] as const;

export function useCurrentTimeMemory() {
  return useQuery({
    queryKey: timeMemoryQueryKey,
    queryFn: getCurrentTimeMemory,
    retry: false,
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
