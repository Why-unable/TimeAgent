// Native-only bootstrap. Loaded lazily from src/bootstrap.ts and never bundled
// into the web build or pulled into tests. Swaps the auth token store to a
// Android Keystore-backed implementation so the token survives cold starts
// without being stored as plaintext, then hands off to notification setup.

import { App } from "@capacitor/app";
import { SecureStorage } from "@aparajita/capacitor-secure-storage";

import { listReminders } from "../api/reminders";
import { getAuthToken, setTokenStore } from "../api/auth-token";
import { queryClient } from "../app/query-client";
import { reminderQueryKey } from "../features/reminders/hooks";
import { syncLocalReminderNotifications } from "../features/notifications/local-sync";
import { markNative } from "../platform";

const TOKEN_KEY = "time-agent.auth-token";
// Poll interval for the app-level reminder→alarm reconciliation. Reminders can
// be created anywhere (e.g. the chat agent), not just on the reminders page, so
// scheduling must not depend on any screen mounting useReminders().
const RECONCILE_INTERVAL_MS = 60_000;

export async function configureNative(): Promise<void> {
  markNative(true);
  setTokenStore({
    async load() {
      const value = await SecureStorage.get(TOKEN_KEY);
      return typeof value === "string" ? value : null;
    },
    async save(token: string) {
      await SecureStorage.set(TOKEN_KEY, token);
    },
    async clear() {
      await SecureStorage.remove(TOKEN_KEY);
    },
  });
}

export async function startNativeServices(): Promise<void> {
  // App-level reconciliation: fetch reminders and (re)schedule OS alarms
  // independently of which screen is mounted. Runs on startup, whenever the app
  // returns to the foreground, and on a slow poll so alarms stay in sync after
  // the agent creates a reminder from the chat page.
  async function reconcileReminderAlarms(): Promise<void> {
    if (!getAuthToken()) return; // Not signed in yet; nothing to schedule.
    try {
      const reminders = await listReminders();
      queryClient.setQueryData(reminderQueryKey, reminders);
      await syncLocalReminderNotifications(reminders);
    } catch {
      // A transient fetch failure must not crash bootstrap; the next tick or
      // foreground event retries.
    }
  }

  await reconcileReminderAlarms();
  window.setInterval(() => void reconcileReminderAlarms(), RECONCILE_INTERVAL_MS);
  void App.addListener("appStateChange", ({ isActive }) => {
    if (isActive) void reconcileReminderAlarms();
  });
}
