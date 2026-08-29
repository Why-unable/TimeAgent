// Native local-notification driver. Imports @capacitor/local-notifications, so
// it is only ever loaded on native (lazily, via the notification sync entry).
//
// Responsibilities:
//  - request the POST_NOTIFICATIONS permission (Android 13+),
//  - create the high-importance "schedule_reminders" channel,
//  - apply a SchedulePlan by scheduling/cancelling OS alarms.
//
// The OS (AlarmManager under the hood) fires these even when the app process is
// dead, which is the whole point: reminders arrive without the app running.

import { LocalNotifications } from "@capacitor/local-notifications";

import type { Reminder } from "../api/reminders";
import { recordTaskExecutionSignal } from "../api/tasks";
import {
  LOCAL_NOTIFICATION_SCHEDULE_VERSION,
  planReminderNotifications,
} from "../features/notifications/local-schedule";
import { recordNativeNotificationSchedules } from "./notification-diagnostics";

const CHANNEL_ID = "schedule_reminders";
const TASK_ACTION_TYPE_ID = "task_reminder_actions";
const PENDING_TASK_ACTIONS_KEY = "time-agent.pending-task-actions";

let channelReady = false;
let tapListenerReady = false;

type PendingTaskAction = {
  taskId: string;
  signalType: "started" | "skipped";
  occurredAt: string;
  idempotencyKey: string;
};

function readPendingTaskActions(): PendingTaskAction[] {
  try {
    const raw = window.localStorage.getItem(PENDING_TASK_ACTIONS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed as PendingTaskAction[] : [];
  } catch {
    return [];
  }
}

function writePendingTaskActions(actions: PendingTaskAction[]): void {
  window.localStorage.setItem(PENDING_TASK_ACTIONS_KEY, JSON.stringify(actions));
}

function queueTaskAction(action: PendingTaskAction): void {
  const actions = readPendingTaskActions();
  if (!actions.some((item) => item.idempotencyKey === action.idempotencyKey)) {
    actions.push(action);
    writePendingTaskActions(actions);
  }
}

async function flushPendingTaskActions(): Promise<void> {
  const remaining: PendingTaskAction[] = [];
  for (const action of readPendingTaskActions()) {
    try {
      await recordTaskExecutionSignal(action.taskId, action.signalType, {
        occurred_at: action.occurredAt,
        idempotency_key: action.idempotencyKey,
      });
    } catch {
      remaining.push(action);
    }
  }
  writePendingTaskActions(remaining);
}

export type NativeReminderPermissionState = {
  display: string;
  exactAlarm: string;
};

/**
 * Route to /reminders when the user taps a reminder notification. Registered
 * once. Uses hash-agnostic history navigation via location assignment on the
 * SPA path (the router picks it up on next load) — kept minimal to avoid
 * coupling the native layer to the router instance.
 */
async function ensureTapListener(): Promise<void> {
  if (tapListenerReady) return;
  await LocalNotifications.addListener("localNotificationActionPerformed", async (event) => {
    const actionId = event.actionId;
    const targetId = event.notification.extra?.targetId;
    const targetType = event.notification.extra?.targetType;
    if (targetType === "task" && typeof targetId === "string" && (actionId === "start" || actionId === "skip")) {
      const signalType = actionId === "start" ? "started" : "skipped";
      const action = {
        taskId: targetId,
        signalType,
        occurredAt: new Date().toISOString(),
        idempotencyKey: `native-${targetId}-${signalType}-${Date.now()}`,
      } satisfies PendingTaskAction;
      try {
        await recordTaskExecutionSignal(targetId, signalType, {
          occurred_at: action.occurredAt,
          idempotency_key: action.idempotencyKey,
        });
      } catch {
        queueTaskAction(action);
      }
      if (window.location.pathname !== "/tasks") {
        window.history.pushState({}, "", "/tasks");
      }
    } else if (window.location.pathname !== "/reminders") {
      window.history.pushState({}, "", "/reminders");
    }
    if (window.location.pathname === "/tasks" || window.location.pathname === "/reminders") {
      window.dispatchEvent(new PopStateEvent("popstate"));
    }
  });
  tapListenerReady = true;
}

async function ensureNotificationSetup(requestDisplayPermission = false): Promise<boolean> {
  const permission = requestDisplayPermission
    ? await LocalNotifications.requestPermissions()
    : await LocalNotifications.checkPermissions();
  if (permission.display !== "granted") return false;

  if (!channelReady) {
    await LocalNotifications.createChannel({
      id: CHANNEL_ID,
      name: "日程提醒",
      description: "会议、截止时间等定时提醒",
      importance: 5, // IMPORTANCE_HIGH: heads-up + sound.
      visibility: 1,
      vibration: true,
    });
    channelReady = true;
  }
  await LocalNotifications.registerActionTypes({
    types: [{
      id: TASK_ACTION_TYPE_ID,
      actions: [
        { id: "start", title: "开始" },
        { id: "skip", title: "跳过" },
      ],
    }],
  });
  await flushPendingTaskActions();
  await ensureTapListener();
  return true;
}

/** Read Android notification and exact-alarm access without prompting. */
export async function getNativeReminderPermissionState(): Promise<NativeReminderPermissionState> {
  const [display, exactAlarm] = await Promise.all([
    LocalNotifications.checkPermissions(),
    LocalNotifications.checkExactNotificationSetting(),
  ]);
  return { display: display.display, exactAlarm: exactAlarm.exact_alarm };
}

/** Must only be called from an explicit user action. */
export async function requestNativeReminderNotificationPermission(): Promise<NativeReminderPermissionState> {
  await ensureNotificationSetup(true);
  return getNativeReminderPermissionState();
}

/** Opens Android's dedicated "Alarms & reminders" settings page. */
export async function requestNativeExactAlarmPermission(): Promise<NativeReminderPermissionState> {
  await LocalNotifications.changeExactNotificationSetting();
  return getNativeReminderPermissionState();
}

/** Reconcile the device's scheduled notifications with the reminder list. */
export async function syncReminderNotifications(reminders: readonly Reminder[]): Promise<void> {
  // Background reconciliation must never surface a permission prompt.  The
  // settings page owns the explicit, user-initiated permission flow.
  const granted = await ensureNotificationSetup();
  if (!granted) return;

  const pending = await LocalNotifications.getPending();
  const existing = pending.notifications.flatMap((item) => {
    const reminderId = item.extra?.reminderId;
    const atValue = item.schedule?.at;
    const at = atValue instanceof Date ? atValue.getTime() : Date.parse(String(atValue ?? ""));
    if (typeof reminderId !== "string" || !Number.isFinite(at)) return [];
    return [{
      id: item.id,
      reminderId,
      title: item.title,
      body: item.body,
      at,
      scheduleVersion: Number(item.extra?.scheduleVersion),
      targetType: typeof item.extra?.targetType === "string" ? item.extra.targetType : undefined,
      targetId: typeof item.extra?.targetId === "string" ? item.extra.targetId : null,
    }];
  });
  const plan = planReminderNotifications(reminders, existing, Date.now());

  if (plan.toCancel.length > 0) {
    await LocalNotifications.cancel({
      notifications: plan.toCancel.map((id) => ({ id })),
    });
  }

  if (plan.toSchedule.length > 0) {
    await recordNativeNotificationSchedules(
      plan.toSchedule.map((item) => ({
        notificationId: item.id,
        scheduledAt: item.at,
        title: item.title,
      })),
    );
    await LocalNotifications.schedule({
      notifications: plan.toSchedule.map((item) => ({
        id: item.id,
        title: item.title,
        body: item.body,
        channelId: CHANNEL_ID,
        // Android auto-groups four or more ungrouped notifications.  Some OEM
        // System UI implementations then render the group's first timestamp on
        // every visible child card.  Keep each reminder in its own group so the
        // notification shade preserves its actual delivery time.
        group: `reminder-${item.id}`,
        actionTypeId: item.targetType === "task" && item.targetId ? TASK_ACTION_TYPE_ID : undefined,
        schedule: { at: new Date(item.at), allowWhileIdle: true },
        extra: {
          reminderId: item.reminderId,
          scheduleVersion: LOCAL_NOTIFICATION_SCHEDULE_VERSION,
          targetType: item.targetType,
          targetId: item.targetId,
        },
      })),
    });
  }
}
