import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const nativePermissionMocks = vi.hoisted(() => ({
  getPermissionState: vi.fn(),
  requestDisplayPermission: vi.fn(),
  requestExactAlarmPermission: vi.fn(),
}));

vi.mock("../src/platform", () => ({ isNativePlatform: () => true }));
vi.mock("../src/features/accounts/hooks", () => ({
  useCurrentUser: () => ({ data: { is_staff: false } }),
}));
vi.mock("../src/native/notification-diagnostics", () => ({
  clearNativeNotificationDiagnostics: vi.fn(),
  getNativeNotificationDiagnostics: vi.fn().mockResolvedValue([]),
}));
vi.mock("../src/features/notifications/local-sync", () => ({
  getNativeReminderPermissionState: nativePermissionMocks.getPermissionState,
  requestNativeReminderNotificationPermission: nativePermissionMocks.requestDisplayPermission,
  requestNativeExactAlarmPermission: nativePermissionMocks.requestExactAlarmPermission,
}));
vi.mock("../src/features/notifications/hooks", () => ({
  useNotificationPreference: () => ({ data: {
    email: "user@example.test", reminder_email_enabled: false, briefing_email_enabled: false,
    reminder_web_push_enabled: false, briefing_web_push_enabled: false,
  }, isLoading: false, isError: false }),
  useNotificationDeliveries: () => ({ data: [], isLoading: false }),
  useWebPushConfig: () => ({ data: { configured: false, public_key: "" } }),
  useWebPushSubscriptions: () => ({ data: [] }),
  useUpdateNotificationPreference: () => ({ mutate: vi.fn() }),
  useCreateWebPushSubscription: () => ({ mutateAsync: vi.fn() }),
  useDeleteWebPushSubscription: () => ({ mutateAsync: vi.fn() }),
}));

import { NotificationSettingsPage } from "../src/pages/notification-settings-page";

describe("native notification permission guidance", () => {
  it("requests notification permission only after the user clicks the button", async () => {
    nativePermissionMocks.getPermissionState.mockResolvedValue({ display: "prompt", exactAlarm: "denied" });
    nativePermissionMocks.requestDisplayPermission.mockResolvedValue({ display: "granted", exactAlarm: "denied" });

    render(<NotificationSettingsPage />);
    expect(await screen.findByText("应用提醒（Android）")).toBeInTheDocument();
    expect(nativePermissionMocks.requestDisplayPermission).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "允许应用通知" }));
    expect(nativePermissionMocks.requestDisplayPermission).toHaveBeenCalledOnce();
  });

  it("opens the exact-alarm setting only after notification access is granted", async () => {
    nativePermissionMocks.getPermissionState.mockResolvedValue({ display: "granted", exactAlarm: "denied" });
    nativePermissionMocks.requestExactAlarmPermission.mockResolvedValue({ display: "granted", exactAlarm: "denied" });

    render(<NotificationSettingsPage />);
    const button = await screen.findByRole("button", { name: "开启精确提醒" });
    expect(button).toBeEnabled();

    await userEvent.click(button);
    expect(nativePermissionMocks.requestExactAlarmPermission).toHaveBeenCalledOnce();
  });
});
