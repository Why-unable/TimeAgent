import { describe, expect, it } from "vitest";

import type { Reminder } from "../src/api/reminders";
import {
  LOCAL_NOTIFICATION_SCHEDULE_VERSION,
  MAX_SCHEDULED,
  planReminderNotifications,
  reminderNotificationId,
} from "../src/features/notifications/local-schedule";

const NOW = Date.parse("2026-07-25T12:00:00Z");

function reminder(overrides: Partial<Reminder> & { id: string }): Reminder {
  return {
    id: overrides.id,
    title: overrides.title ?? "Reminder",
    trigger_at: overrides.trigger_at ?? "2026-07-25T13:00:00Z",
    timezone: "Asia/Shanghai",
    status: overrides.status ?? "pending",
    deduplication_key: overrides.deduplication_key ?? `dedup-${overrides.id}`,
  } as Reminder;
}

describe("reminderNotificationId", () => {
  it("is deterministic and positive", () => {
    const id = reminderNotificationId("abc-123");
    expect(id).toBe(reminderNotificationId("abc-123"));
    expect(id).toBeGreaterThan(0);
    expect(id).toBeLessThanOrEqual(0x7fffffff);
  });

  it("differs for different reminders", () => {
    expect(reminderNotificationId("a")).not.toBe(reminderNotificationId("b"));
  });
});

describe("planReminderNotifications", () => {
  it("schedules future pending reminders", () => {
    const plan = planReminderNotifications(
      [reminder({ id: "r1", trigger_at: "2026-07-25T13:00:00Z", title: "Meeting" })],
      [],
      NOW,
    );
    expect(plan.toSchedule).toHaveLength(1);
    expect(plan.toSchedule[0]).toMatchObject({
      reminderId: "r1",
      title: "Meeting",
      at: Date.parse("2026-07-25T13:00:00Z"),
    });
    expect(plan.toCancel).toEqual([]);
  });

  it("ignores past reminders", () => {
    const plan = planReminderNotifications(
      [reminder({ id: "past", trigger_at: "2026-07-25T11:00:00Z" })],
      [],
      NOW,
    );
    expect(plan.toSchedule).toEqual([]);
  });

  it("ignores non-pending reminders", () => {
    const plan = planReminderNotifications(
      [
        reminder({ id: "sent", status: "sent", trigger_at: "2026-07-25T13:00:00Z" }),
        reminder({ id: "cancelled", status: "cancelled", trigger_at: "2026-07-25T14:00:00Z" }),
      ],
      [],
      NOW,
    );
    expect(plan.toSchedule).toEqual([]);
  });

  it("cancels device notifications that are no longer desired", () => {
    const staleId = reminderNotificationId("deleted-reminder");
    const currentId = reminderNotificationId("r1");
    const plan = planReminderNotifications(
      [reminder({ id: "r1", trigger_at: "2026-07-25T13:00:00Z" })],
      [
        {
          id: staleId,
          reminderId: "deleted-reminder",
          title: "Deleted",
          at: Date.parse("2026-07-25T13:00:00Z"),
        },
        {
          id: currentId,
          reminderId: "r1",
          title: "Reminder",
          at: Date.parse("2026-07-25T13:00:00Z"),
          scheduleVersion: LOCAL_NOTIFICATION_SCHEDULE_VERSION,
        },
      ],
      NOW,
    );
    // r1 stays scheduled; the stale one is cancelled.
    expect(plan.toCancel).toEqual([staleId]);
    expect(plan.toSchedule).toEqual([]);
  });

  it("does not reschedule an unchanged reminder", () => {
    const id = reminderNotificationId("r1");
    const plan = planReminderNotifications(
      [reminder({ id: "r1", trigger_at: "2026-07-25T13:00:00Z" })],
      [{
        id,
        reminderId: "r1",
        title: "Reminder",
        at: Date.parse("2026-07-25T13:00:00Z"),
        scheduleVersion: LOCAL_NOTIFICATION_SCHEDULE_VERSION,
      }],
      NOW,
    );
    expect(plan.toCancel).toEqual([]);
    expect(plan.toSchedule).toEqual([]);
  });

  it("reschedules a reminder when its time or title changes", () => {
    const id = reminderNotificationId("r1");
    const plan = planReminderNotifications(
      [reminder({ id: "r1", title: "New title", trigger_at: "2026-07-25T14:00:00Z" })],
      [{
        id,
        reminderId: "r1",
        title: "Old title",
        at: Date.parse("2026-07-25T13:00:00Z"),
      }],
      NOW,
    );
    expect(plan.toCancel).toEqual([]);
    expect(plan.toSchedule).toEqual([
      expect.objectContaining({
        id,
        reminderId: "r1",
        title: "New title",
        at: Date.parse("2026-07-25T14:00:00Z"),
      }),
    ]);
  });

  it("upgrades a pending notification created by an older presentation contract", () => {
    const id = reminderNotificationId("r1");
    const plan = planReminderNotifications(
      [reminder({ id: "r1", trigger_at: "2026-07-25T13:00:00Z" })],
      [{
        id,
        reminderId: "r1",
        title: "Reminder",
        at: Date.parse("2026-07-25T13:00:00Z"),
        scheduleVersion: 1,
      }],
      NOW,
    );
    expect(plan.toSchedule).toHaveLength(1);
  });

  it("does not cancel notifications owned by another feature", () => {
    const plan = planReminderNotifications([], [], NOW);
    expect(plan.toCancel).toEqual([]);
  });

  it("caps the rolling window and cancels overflow already on device", () => {
    const reminders = Array.from({ length: MAX_SCHEDULED + 5 }, (_, i) =>
      reminder({
        id: `r${i}`,
        // Each one hour further out; all in the future.
        trigger_at: new Date(NOW + (i + 1) * 3_600_000).toISOString(),
      }),
    );
    const plan = planReminderNotifications(reminders, [], NOW);
    expect(plan.toSchedule).toHaveLength(MAX_SCHEDULED);
    // The soonest ones are kept.
    expect(plan.toSchedule[0].reminderId).toBe("r0");
  });
});
