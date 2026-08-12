import type { WebPushSubscriptionCreate } from "../../api/notifications";

export type BrowserPushState = "unsupported" | "not_requested" | "granted" | "denied";

export function isChromeUsingFcm(userAgent = navigator.userAgent): boolean {
  return /\bChrome\/\d+/i.test(userAgent) && !/\b(?:Edg|OPR|SamsungBrowser)\/\d+/i.test(userAgent);
}

export function browserPushState(): BrowserPushState {
  if (
    !navigator.serviceWorker ||
    !("PushManager" in window) ||
    !("Notification" in window)
  ) {
    return "unsupported";
  }
  if (Notification.permission === "granted") return "granted";
  if (Notification.permission === "denied") return "denied";
  return "not_requested";
}

export async function subscribeBrowser(publicKey: string): Promise<WebPushSubscriptionCreate> {
  if ((await Notification.requestPermission()) !== "granted") {
    throw new Error("notification_permission_denied");
  }
  // Idempotent: reuses the boot-time registration when present, otherwise
  // registers now (e.g. dev, where the SW is not registered on startup).
  await navigator.serviceWorker.register("/sw.js?v=3");
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  });
  const json = subscription.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth) {
    throw new Error("invalid_push_subscription");
  }
  return { endpoint: json.endpoint, p256dh: json.keys.p256dh, auth: json.keys.auth };
}

export async function unsubscribeBrowser(): Promise<void> {
  const serviceWorker = navigator.serviceWorker;
  if (!serviceWorker || typeof serviceWorker.getRegistration !== "function") return;
  const registration = await serviceWorker.getRegistration();
  const subscription = await registration?.pushManager.getSubscription();
  await subscription?.unsubscribe();
}

export async function currentBrowserPushEndpoint(): Promise<string | null> {
  const serviceWorker = navigator.serviceWorker;
  if (!serviceWorker || typeof serviceWorker.getRegistration !== "function") return null;
  const registration = await serviceWorker.getRegistration();
  const subscription = await registration?.pushManager.getSubscription();
  return subscription?.endpoint ?? null;
}

function urlBase64ToUint8Array(value: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const raw = atob((value + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (character) => character.charCodeAt(0));
}
