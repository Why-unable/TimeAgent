import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createWebPushSubscription,
  deleteWebPushSubscription,
  getNotificationPreference,
  getWebPushConfig,
  listNotificationDeliveries,
  listWebPushSubscriptions,
  unsubscribeWebPushEndpoint,
  updateNotificationPreference,
} from "../../api/notifications";

export const notificationKeys = {
  preference: ["notifications", "preference"] as const,
  deliveries: ["notifications", "deliveries"] as const,
  pushConfig: ["notifications", "push-config"] as const,
  subscriptions: ["notifications", "subscriptions"] as const,
};

export const useNotificationPreference = () =>
  useQuery({ queryKey: notificationKeys.preference, queryFn: getNotificationPreference });
export const useNotificationDeliveries = () =>
  useQuery({ queryKey: notificationKeys.deliveries, queryFn: listNotificationDeliveries });
export const useWebPushConfig = () =>
  useQuery({ queryKey: notificationKeys.pushConfig, queryFn: getWebPushConfig });
export const useWebPushSubscriptions = () =>
  useQuery({ queryKey: notificationKeys.subscriptions, queryFn: listWebPushSubscriptions });

export function useUpdateNotificationPreference() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: updateNotificationPreference,
    onSuccess: (data) => client.setQueryData(notificationKeys.preference, data),
  });
}

export function useCreateWebPushSubscription() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: createWebPushSubscription,
    onSuccess: () => client.invalidateQueries({ queryKey: notificationKeys.subscriptions }),
  });
}

export function useDeleteWebPushSubscription() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: deleteWebPushSubscription,
    onSuccess: () => client.invalidateQueries({ queryKey: notificationKeys.subscriptions }),
  });
}

export function useUnsubscribeWebPushEndpoint() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: unsubscribeWebPushEndpoint,
    onSuccess: () => client.invalidateQueries({ queryKey: notificationKeys.subscriptions }),
  });
}
