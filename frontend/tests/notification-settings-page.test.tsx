import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NotificationSettingsPage } from "../src/pages/notification-settings-page";

const preference = {
  email: "user@example.test",
  reminder_console_enabled: true,
  reminder_email_enabled: false,
  reminder_web_push_enabled: false,
  briefing_console_enabled: true,
  briefing_email_enabled: false,
  briefing_web_push_enabled: false,
  updated_at: "2026-07-21T00:00:00Z",
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NotificationSettingsPage />
    </QueryClientProvider>,
  );
}

function mockApi({ subscriptions = [] as object[] } = {}) {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requests.push({ url, init });
    if (url.endsWith("notification-preferences/me/") && (init?.method ?? "GET") === "GET") return new Response(JSON.stringify(preference));
    if (url.endsWith("notification-preferences/me/") && init?.method === "PATCH") return new Response(JSON.stringify({ ...preference, ...JSON.parse(String(init.body)) }));
    if (url.endsWith("preferences/me/") && (init?.method ?? "GET") === "GET") return new Response(JSON.stringify({
      daily_briefing_enabled: false,
      briefing_time: "08:00:00",
    }));
    if (url.endsWith("preferences/me/") && init?.method === "PATCH") return new Response(JSON.stringify({
      daily_briefing_enabled: false,
      briefing_time: "08:00:00",
      ...JSON.parse(String(init.body)),
    }));
    if (url.endsWith("notification-deliveries/")) return new Response(JSON.stringify([
      { id: "delivery-console", source_type: "reminder", source_id: null, channel_type: "console", status: "sent", subject: "Development-only reminder", scheduled_at: "2026-07-21T00:00:00Z", queued_at: null, sending_at: null, sent_at: "2026-07-21T00:00:01Z", failed_at: null, attempt_count: 1, next_retry_at: null, provider_message_id: "", failure_code: "", failure_reason: "", created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:01Z" },
      { id: "delivery-1", source_type: "reminder", source_id: null, channel_type: "email", status: "failed", subject: "Take medicine", scheduled_at: "2026-07-21T00:00:00Z", queued_at: null, sending_at: null, sent_at: null, failed_at: "2026-07-21T00:00:01Z", attempt_count: 4, next_retry_at: null, provider_message_id: "", failure_code: "permanent_notification_error", failure_reason: "Invalid mailbox", created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:01Z" },
    ]));
    if (url.endsWith("web-push/config/")) return new Response(JSON.stringify({ configured: true, public_key: "AQID" }));
    if (url.endsWith("web-push/subscriptions/") && (init?.method ?? "GET") === "GET") return new Response(JSON.stringify(subscriptions));
    if (url.endsWith("web-push/subscriptions/") && init?.method === "POST") return new Response(JSON.stringify({ id: "subscription-1", endpoint_hint: "https://push.example…", enabled: true, last_used_at: null, invalidated_at: null, created_at: "2026-07-21T00:00:00Z" }), { status: 201 });
    if (url.includes("web-push/subscriptions/") && init?.method === "DELETE") return new Response(null, { status: 204 });
    throw new Error(`Unexpected request: ${url}`);
  }));
  return requests;
}

describe("NotificationSettingsPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: undefined,
    });
  });

  it("shows unsupported browser state and delivery failure reason", async () => {
    mockApi();
    renderPage();
    expect(await screen.findByText("浏览器不支持推送通知")).toBeInTheDocument();
    expect(await screen.findByText(/Invalid mailbox/)).toBeInTheDocument();
    expect(screen.queryByText("Development-only reminder")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "启用浏览器通知" })).toBeDisabled();
  });

  it("enables a daily briefing", async () => {
    const requests = mockApi();
    renderPage();

    await userEvent.click(await screen.findByRole("checkbox", { name: "启用定时简报" }));

    expect(
      requests.some(
        (item) =>
          item.url.endsWith("preferences/me/") &&
          item.init?.method === "PATCH" &&
          String(item.init.body).includes("daily_briefing_enabled"),
      ),
    ).toBe(true);
  });

  it("shows permission denial after an explicit user click", async () => {
    mockApi();
    vi.stubGlobal("PushManager", class PushManager {});
    vi.stubGlobal("Notification", { permission: "default", requestPermission: vi.fn().mockResolvedValue("denied") });
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { register: vi.fn() } });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "启用浏览器通知" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("拒绝了通知权限");
  });

  it("creates and uploads a browser subscription", async () => {
    const requests = mockApi();
    const pushSubscription = { toJSON: () => ({ endpoint: "https://push.example.test/id", keys: { p256dh: "key", auth: "auth" } }) };
    const registration = { pushManager: { subscribe: vi.fn().mockResolvedValue(pushSubscription) } };
    vi.stubGlobal("PushManager", class PushManager {});
    vi.stubGlobal("Notification", { permission: "granted", requestPermission: vi.fn().mockResolvedValue("granted") });
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { register: vi.fn().mockResolvedValue(registration), ready: Promise.resolve(registration) } });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "启用浏览器通知" }));
    const request = requests.find((item) => item.init?.method === "POST");
    expect(JSON.parse(String(request?.init?.body))).toEqual({ endpoint: "https://push.example.test/id", p256dh: "key", auth: "auth" });
  });

  it("unsubscribes in the browser and removes the backend subscription", async () => {
    const requests = mockApi({ subscriptions: [{ id: "subscription-1", endpoint_hint: "push…", enabled: true, last_used_at: null, invalidated_at: null, created_at: "2026-07-21T00:00:00Z" }] });
    const unsubscribe = vi.fn().mockResolvedValue(true);
    vi.stubGlobal("PushManager", class PushManager {});
    vi.stubGlobal("Notification", { permission: "granted", requestPermission: vi.fn() });
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { getRegistration: vi.fn().mockResolvedValue({ pushManager: { getSubscription: vi.fn().mockResolvedValue({ unsubscribe }) } }) } });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "取消订阅" }));
    expect(unsubscribe).toHaveBeenCalledOnce();
    expect(requests.some((item) => item.url.endsWith("/subscription-1/") && item.init?.method === "DELETE")).toBe(true);
  });
});
