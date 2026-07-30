// Platform-safe entry point for syncing on-device reminder notifications.
//
// Safe to call from shared React code: on web it is a no-op, on native it lazily
// loads the Capacitor driver (keeping the plugin out of the web bundle).

import { listReminders, type Reminder } from "../../api/reminders";
import { isNativePlatform } from "../../platform";

export type NativeReminderPermissionState = {
  display: string;
  exactAlarm: string;
};

export async function syncLocalReminderNotifications(
  reminders: readonly Reminder[],
): Promise<void> {
  if (!isNativePlatform()) return;
  const driver = await import("../../native/local-notifications");
  await driver.syncReminderNotifications(reminders);
}

export async function getNativeReminderPermissionState(): Promise<NativeReminderPermissionState | null> {
  if (!isNativePlatform()) return null;
  const driver = await import("../../native/local-notifications");
  return driver.getNativeReminderPermissionState();
}

export async function requestNativeReminderNotificationPermission(): Promise<NativeReminderPermissionState | null> {
  if (!isNativePlatform()) return null;
  const driver = await import("../../native/local-notifications");
  const state = await driver.requestNativeReminderNotificationPermission();
  if (state.display === "granted") {
    await driver.syncReminderNotifications(await listReminders());
  }
  return state;
}

export async function requestNativeExactAlarmPermission(): Promise<NativeReminderPermissionState | null> {
  if (!isNativePlatform()) return null;
  const driver = await import("../../native/local-notifications");
  return driver.requestNativeExactAlarmPermission();
}
