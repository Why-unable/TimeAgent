import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelEvent,
  createEvent,
  listEvents,
  type CreateCalendarEvent,
  type EventListParams,
  type UpdateCalendarEvent,
  updateEvent,
} from "../../api/events";

export const eventQueryKey = ["events"] as const;

export function useEvents(params: EventListParams) {
  return useQuery({
    queryKey: [...eventQueryKey, params],
    queryFn: () => listEvents(params),
    retry: false,
  });
}

export function useCreateEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateCalendarEvent) => createEvent(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: eventQueryKey }),
  });
}

export function useUpdateEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      eventId,
      expectedVersion,
      input,
    }: {
      eventId: string;
      expectedVersion: number;
      input: UpdateCalendarEvent;
    }) => updateEvent(eventId, expectedVersion, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: eventQueryKey }),
  });
}

export function useCancelEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ eventId, expectedVersion }: { eventId: string; expectedVersion: number }) =>
      cancelEvent(eventId, expectedVersion),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: eventQueryKey }),
  });
}
