// Platform-safe entry point for syncing on-device reminder notifications.
//
// Safe to call from shared React code: on web it is a no-op, on native it lazily
// loads the Capacitor driver (keeping the plugin out of the web bundle).

import type { Reminder } from "../../api/reminders";
import { isNativePlatform } from "../../platform";

export async function syncLocalReminderNotifications(
  reminders: readonly Reminder[],
): Promise<void> {
  if (!isNativePlatform()) return;
  const driver = await import("../../native/local-notifications");
  await driver.syncReminderNotifications(reminders);
}
