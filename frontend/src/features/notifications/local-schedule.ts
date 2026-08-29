// Pure scheduling logic for local (on-device) reminder notifications.
//
// Kept free of Capacitor imports so it is fully unit-testable. Given the current
// reminder list and what is already scheduled on the device, it computes which
// notifications to schedule and which to cancel. The native layer applies the
// result via @capacitor/local-notifications.

import type { Reminder } from "../../api/reminders";

export interface PlannedNotification {
  /** Stable numeric id derived from the reminder uuid (plugin requires int ids). */
  id: number;
  reminderId: string;
  title: string;
  body: string;
  /** Epoch milliseconds at which the OS should fire the notification. */
  at: number;
  targetType?: string;
  targetId?: string | null;
}

export interface SchedulePlan {
  toSchedule: PlannedNotification[];
  toCancel: number[];
}

export interface ExistingNotification {
  id: number;
  reminderId: string;
  title: string;
  body?: string;
  at: number;
  scheduleVersion?: number;
  targetType?: string;
  targetId?: string | null;
}

// Android caps the number of pending alarms; keep a rolling window of the
// soonest upcoming reminders rather than scheduling everything.
export const MAX_SCHEDULED = 60;

/**
 * Increment when the native notification presentation contract changes.
 * Existing pending alarms are then safely re-created once on the next sync.
 */
export const LOCAL_NOTIFICATION_SCHEDULE_VERSION = 4;

export function reminderNotificationBody(reminder: Reminder): string {
  if (reminder.offset_minutes === 1440) return `一天后：${reminder.title}`;
  if (reminder.offset_minutes === 15) return `15 分钟后：${reminder.title}`;
  if (reminder.offset_minutes === 0) return `现在：${reminder.title}`;
  if (reminder.offset_minutes != null) return `${reminder.offset_minutes} 分钟后：${reminder.title}`;
  return reminder.title;
}

/**
 * Derive a stable positive 31-bit integer id from a reminder uuid. The plugin
 * identifies notifications by int, but reminders are uuids, so we hash. FNV-1a
 * is deterministic and collision-resistant enough for this small set.
 */
export function reminderNotificationId(reminderId: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < reminderId.length; i += 1) {
    hash ^= reminderId.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  // Force non-negative and keep within Java int range (avoid 0, some plugins reject it).
  return (hash & 0x7fffffff) || 1;
}

/**
 * Compute the schedule plan.
 *
 * @param reminders  Current reminders from the backend.
 * @param existing  Reminder notifications currently pending on the device.
 * @param now  Current time in epoch ms (injectable for tests).
 */
export function planReminderNotifications(
  reminders: readonly Reminder[],
  existing: readonly ExistingNotification[],
  now: number,
): SchedulePlan {
  // Only future, still-actionable reminders warrant a local notification.
  const upcoming = reminders
    .filter((reminder) => reminder.status === "pending")
    .map((reminder) => ({ reminder, at: Date.parse(reminder.trigger_at) }))
    .filter(({ at }) => Number.isFinite(at) && at > now)
    .sort((a, b) => a.at - b.at)
    .slice(0, MAX_SCHEDULED);

  const desired: PlannedNotification[] = upcoming.map(({ reminder, at }) => ({
    id: reminderNotificationId(reminder.id),
    reminderId: reminder.id,
    title: "Time Agent 提醒",
    body: reminderNotificationBody(reminder),
    at,
    targetType: reminder.target_type,
    targetId: reminder.target_id,
  }));

  const desiredIds = new Set(desired.map((item) => item.id));
  const existingByReminder = new Map(existing.map((item) => [item.reminderId, item]));
  const toSchedule = desired.filter((item) => {
    const current = existingByReminder.get(item.reminderId);
    return !current
      || current.id !== item.id
      || current.title !== item.title
      || current.body !== item.body
      || current.at !== item.at
      || current.targetType !== item.targetType
      || current.targetId !== item.targetId
      || current.scheduleVersion !== LOCAL_NOTIFICATION_SCHEDULE_VERSION;
  });
  // Cancel anything on the device that is no longer a desired future reminder
  // (fired, cancelled, deleted, rescheduled into the past, or pushed out of the
  // rolling window).
  const toCancel = Array.from(
    new Set(
      existing
        .filter((item) => !desiredIds.has(item.id))
        .map((item) => item.id),
    ),
  );

  return { toSchedule, toCancel };
}
