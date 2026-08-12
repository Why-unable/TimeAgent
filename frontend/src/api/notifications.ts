import { apiRequest } from "./client";
import type { components } from "./generated/schema";

export type NotificationPreference = components["schemas"]["NotificationPreference"];
export type NotificationDelivery = components["schemas"]["NotificationDelivery"];
export type WebPushConfig = components["schemas"]["WebPushConfig"];
export type WebPushSubscription = components["schemas"]["WebPushSubscription"];
export type WebPushSubscriptionCreate = components["schemas"]["WebPushSubscriptionCreate"];

export const getNotificationPreference = () =>
  apiRequest<NotificationPreference>("/api/v1/notification-preferences/me/");

export function updateNotificationPreference(input: Partial<NotificationPreference>) {
  return apiRequest<NotificationPreference>("/api/v1/notification-preferences/me/", {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export const listNotificationDeliveries = () =>
  apiRequest<NotificationDelivery[]>("/api/v1/notification-deliveries/");
export const getWebPushConfig = () =>
  apiRequest<WebPushConfig>("/api/v1/web-push/config/");
export const listWebPushSubscriptions = () =>
  apiRequest<WebPushSubscription[]>("/api/v1/web-push/subscriptions/");

export function createWebPushSubscription(input: WebPushSubscriptionCreate) {
  return apiRequest<WebPushSubscription>("/api/v1/web-push/subscriptions/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export const deleteWebPushSubscription = (id: string) =>
  apiRequest<void>(`/api/v1/web-push/subscriptions/${id}/`, { method: "DELETE" });

export const unsubscribeWebPushEndpoint = (endpoint: string) =>
  apiRequest<void>("/api/v1/web-push/subscriptions/unsubscribe/", {
    method: "POST",
    body: JSON.stringify({ endpoint }),
  });
