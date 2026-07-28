import type { CalendarEvent } from "../../api/events";
import type { Task } from "../../api/tasks";
import type { TodaySummary } from "../../api/today";
import { formatTimeInUserTimezone } from "../../utils/datetime";

export type TimelineEntry =
  | { kind: "event"; id: string; title: string; startAt: string; endAt: string; detail: string }
  | { kind: "task"; id: string; title: string; startAt: string; endAt: string; detail: string };

export function getTimeline(summary: TodaySummary): TimelineEntry[] {
  const events: TimelineEntry[] = summary.events.map((event) => ({
    kind: "event",
    id: event.id,
    title: event.title,
    startAt: event.start_at,
    endAt: event.end_at,
    detail: event.location || "日程",
  }));
  const tasks: TimelineEntry[] = summary.planned_tasks.flatMap((task) =>
    task.planned_start_at && task.planned_end_at
      ? [{
          kind: "task" as const,
          id: task.id,
          title: task.title,
          startAt: task.planned_start_at,
          endAt: task.planned_end_at,
          detail: task.project || "计划任务",
        }]
      : [],
  );
  return [...events, ...tasks].sort((left, right) => left.startAt.localeCompare(right.startAt));
}

export function formatCountdown(minutes: number | null): string {
  if (minutes === null) return "今天没有后续日程";
  if (minutes === 0) return "即将开始";
  if (minutes < 60) return `${minutes} 分钟后`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder === 0 ? `${hours} 小时后` : `${hours} 小时 ${remainder} 分钟后`;
}

export function countPendingTasks(summary: TodaySummary): number {
  return summary.planned_tasks.length + summary.due_tasks.length + summary.overdue_tasks.length;
}

export function getPendingTasks(summary: TodaySummary): Task[] {
  return [...summary.planned_tasks, ...summary.due_tasks, ...summary.overdue_tasks];
}

export function getNextEventLabel(summary: TodaySummary): string {
  if (!summary.next_event) return "暂未安排后续日程";
  return `${formatTimeInUserTimezone(summary.next_event.start_at, summary.timezone)} ${summary.next_event.title}`;
}

export function getNextEvent(summary: TodaySummary): CalendarEvent | null {
  return summary.next_event ?? null;
}
