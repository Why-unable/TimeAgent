import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelReminder,
  createReminder,
  listReminders,
  type CreateReminder,
} from "../../api/reminders";

export const reminderQueryKey = ["reminders"] as const;

export function useReminders() {
  return useQuery({
    queryKey: reminderQueryKey,
    queryFn: listReminders,
    refetchInterval: 30_000,
    retry: false,
  });
}

export function useCreateReminder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateReminder) => createReminder(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: reminderQueryKey }),
  });
}

export function useCancelReminder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: cancelReminder,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: reminderQueryKey }),
  });
}
