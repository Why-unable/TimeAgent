import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import {
  cancelReminder,
  createReminder,
  listReminders,
  type CreateReminder,
  type Reminder,
} from "../../api/reminders";
import { syncLocalReminderNotifications } from "../notifications/local-sync";

export const reminderQueryKey = ["reminders"] as const;

export function useReminders() {
  const query = useQuery({
    queryKey: reminderQueryKey,
    queryFn: listReminders,
    refetchInterval: 30_000,
    retry: false,
  });

  // Keep on-device local notifications in sync with the reminder list. No-op on
  // web; on native this (re)schedules OS alarms so reminders fire even when the
  // app is killed. Driven by the fetched data so it re-runs on every refresh.
  const reminders = query.data;
  useEffect(() => {
    if (!reminders) return;
    void syncLocalReminderNotifications(reminders as Reminder[]);
  }, [reminders]);

  return query;
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
