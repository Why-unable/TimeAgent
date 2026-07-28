import { registerPlugin } from "@capacitor/core";

export type NotificationDiagnosticEntry = {
  kind: "scheduled" | "fired";
  notificationId: number;
  scheduledAt?: number;
  recordedAt: number;
  title?: string;
};

type NotificationDiagnosticsPlugin = {
  recordSchedules(options: { entries: Array<{ notificationId: number; scheduledAt: number; title: string }> }): Promise<void>;
  getEntries(): Promise<{ entries: NotificationDiagnosticEntry[] }>;
  clearEntries(): Promise<void>;
};

const plugin = registerPlugin<NotificationDiagnosticsPlugin>("NotificationDiagnostics");

export async function recordNativeNotificationSchedules(entries: Array<{ notificationId: number; scheduledAt: number; title: string }>): Promise<void> {
  if (entries.length > 0) await plugin.recordSchedules({ entries });
}

export async function getNativeNotificationDiagnostics(): Promise<NotificationDiagnosticEntry[]> {
  return (await plugin.getEntries()).entries;
}

export async function clearNativeNotificationDiagnostics(): Promise<void> {
  await plugin.clearEntries();
}
