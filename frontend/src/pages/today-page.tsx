import {
  AlertTriangle,
  ArrowRight,
  Bell,
  CalendarClock,
  CheckCircle2,
  CircleCheck,
  Clock3,
  Timer,
} from "lucide-react";
import { Link } from "react-router-dom";

import type { CalendarEvent } from "../api/events";
import type { Task } from "../api/tasks";
import type { TodaySummary } from "../api/today";
import { useCompleteTodayTask, useTodaySummary } from "../features/today/hooks";
import {
  formatDateKey,
  formatInUserTimezone,
  formatTimeInUserTimezone,
} from "../utils/datetime";

type TimelineEntry =
  | { kind: "event"; id: string; title: string; startAt: string; endAt: string; detail: string }
  | { kind: "task"; id: string; title: string; startAt: string; endAt: string; detail: string };

function getTimeline(summary: TodaySummary): TimelineEntry[] {
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

function formatCountdown(minutes: number | null) {
  if (minutes === null) return "今天没有后续日程";
  if (minutes === 0) return "即将开始";
  if (minutes < 60) return `${minutes} 分钟后`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder === 0 ? `${hours} 小时后` : `${hours} 小时 ${remainder} 分钟后`;
}

function TaskList({
  title,
  tasks,
  timezone,
  tone,
  onComplete,
  completing,
}: {
  title: string;
  tasks: Task[];
  timezone: string;
  tone: "cyan" | "amber" | "red";
  onComplete: (taskId: string) => void;
  completing: boolean;
}) {
  const tones = {
    cyan: "border-cyan-300/20 bg-cyan-300/5 text-cyan-200",
    amber: "border-amber-300/20 bg-amber-300/5 text-amber-100",
    red: "border-red-400/20 bg-red-400/5 text-red-100",
  };
  return (
    <section className={`rounded-2xl border p-5 ${tones[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold">{title}</h3>
        <span className="rounded-full bg-slate-950/50 px-3 py-1 text-xs">{tasks.length} 项</span>
      </div>
      <div className="mt-4 space-y-3">
        {tasks.length === 0 && <p className="text-sm opacity-60">暂无任务</p>}
        {tasks.map((task) => (
          <article key={task.id} className="flex items-start justify-between gap-3 rounded-xl bg-slate-950/50 p-4">
            <div className="min-w-0">
              <h4 className="font-medium text-slate-100">{task.title}</h4>
              <p className="mt-1 text-xs opacity-70">
                {task.due_at
                  ? `截止 ${formatInUserTimezone(task.due_at, timezone)}`
                  : task.planned_start_at
                    ? `计划 ${formatTimeInUserTimezone(task.planned_start_at, timezone)}`
                    : "未设置时间"}
              </p>
            </div>
            <button
              type="button"
              aria-label={`完成任务：${task.title}`}
              disabled={completing}
              onClick={() => onComplete(task.id)}
              className="shrink-0 rounded-lg p-2 text-emerald-300 hover:bg-emerald-400/10 disabled:opacity-50"
            >
              <CircleCheck size={19} />
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}

function NextEventCard({ event, minutes, timezone }: { event: CalendarEvent | null; minutes: number | null; timezone: string }) {
  return (
    <section className="rounded-2xl border border-cyan-300/20 bg-gradient-to-br from-cyan-300/10 to-violet-400/5 p-5">
      <div className="flex items-center gap-2 text-sm text-cyan-200"><Timer size={17} />下一个日程</div>
      {event ? (
        <>
          <h3 className="mt-4 text-xl font-semibold">{event.title}</h3>
          <p className="mt-2 text-sm text-slate-300">
            {formatTimeInUserTimezone(event.start_at, timezone)}–{formatTimeInUserTimezone(event.end_at, timezone)}
            {event.location ? ` · ${event.location}` : ""}
          </p>
          <p className="mt-5 text-2xl font-semibold text-cyan-200">{formatCountdown(minutes)}</p>
        </>
      ) : (
        <div className="mt-5 flex items-center gap-2 text-slate-400"><CheckCircle2 size={20} />{formatCountdown(null)}</div>
      )}
    </section>
  );
}

function MobileTodayOverview({ data, timeline }: { data: TodaySummary; timeline: TimelineEntry[] }) {
  const taskCount = data.planned_tasks.length + data.due_tasks.length + data.overdue_tasks.length;
  const nextEventLabel = data.next_event
    ? `${formatTimeInUserTimezone(data.next_event.start_at, data.timezone)} ${data.next_event.title}`
    : "暂未安排后续日程";

  return (
    <section className="rounded-[2rem] border border-cyan-300/20 bg-gradient-to-br from-slate-800 to-slate-900 p-6 shadow-[0_24px_55px_-34px_rgba(34,211,238,0.65)] lg:hidden">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-base font-medium text-cyan-200">今日节奏</p>
          <h3 className="mt-2 text-2xl font-semibold text-white">
            {timeline.length === 0 && taskCount === 0 ? "今天很轻松" : "按自己的节奏来"}
          </h3>
        </div>
        <span className="rounded-full bg-cyan-300/10 px-4 py-2 text-sm font-medium text-cyan-100">
          {timeline.length} 项安排
        </span>
      </div>
      <p className="mt-4 text-base text-slate-400">{nextEventLabel}</p>
      <div className="mt-6 grid grid-cols-3 divide-x divide-white/10 rounded-2xl bg-slate-950/60 py-4">
        <div className="px-3 text-center"><p className="text-2xl font-semibold text-white">{data.events.length}</p><p className="mt-1 text-sm text-slate-500">日程</p></div>
        <div className="px-3 text-center"><p className="text-2xl font-semibold text-white">{taskCount}</p><p className="mt-1 text-sm text-slate-500">任务</p></div>
        <div className="px-3 text-center"><p className="text-2xl font-semibold text-white">{data.pending_reminders.length}</p><p className="mt-1 text-sm text-slate-500">提醒</p></div>
      </div>
    </section>
  );
}

export function TodayPage() {
  const summary = useTodaySummary();
  const completeTask = useCompleteTodayTask();

  if (summary.isPending) {
    return <p className="mx-auto max-w-6xl text-slate-400">正在汇总今天的安排…</p>;
  }
  if (summary.isError || !summary.data) {
    return (
      <div role="alert" className="mx-auto max-w-6xl rounded-xl border border-amber-400/30 bg-amber-400/10 p-5 text-amber-100">
        无法读取今日工作台，请确认登录状态后重试。
      </div>
    );
  }

  const data = summary.data;
  const timeline = getTimeline(data);
  const complete = (taskId: string) => completeTask.mutate(taskId);

  return (
    <section className="mx-auto max-w-6xl">
      <div className="flex flex-wrap items-end justify-between gap-5 lg:gap-5">
        <div>
          <p className="hidden text-sm font-medium text-cyan-300 lg:block">Phase 3 · 每日工作台</p>
          <div className="mt-2 flex items-center gap-3">
            <Clock3 className="text-cyan-300" size={31} />
            <h2 className="text-4xl font-semibold sm:text-3xl">今天</h2>
          </div>
          <p className="mt-3 text-base text-slate-400 lg:mt-3">{formatDateKey(data.date)}<span className="hidden lg:inline"> · {data.timezone}</span></p>
        </div>
        <div className="hidden gap-2 sm:gap-3 lg:flex">
          <Link to="/calendar" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm font-medium text-slate-200 hover:border-cyan-300/30 sm:px-4">
            日历 <ArrowRight size={15} />
          </Link>
          <Link to="/tasks" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm font-medium text-slate-200 hover:border-cyan-300/30 sm:px-4">
            任务 <ArrowRight size={15} />
          </Link>
        </div>
      </div>

      <div className="mt-5 lg:hidden">
        <MobileTodayOverview data={data} timeline={timeline} />
      </div>

      {timeline.length === 0 && data.planned_tasks.length === 0 && data.due_tasks.length === 0 && data.overdue_tasks.length === 0 && (
        <div className="mt-5 grid grid-cols-2 gap-4 lg:hidden">
          <Link to="/calendar" className="min-h-40 rounded-3xl border border-cyan-300/20 bg-cyan-300/10 p-5 text-left text-cyan-100 transition active:scale-[0.98]">
            <CalendarClock size={28} />
            <span className="mt-5 block text-xl font-semibold">安排日程</span>
            <span className="mt-2 block text-base text-cyan-100/70">为今天留出时间</span>
          </Link>
          <Link to="/chat" className="min-h-40 rounded-3xl border border-violet-300/20 bg-violet-300/10 p-5 text-left text-violet-100 transition active:scale-[0.98]">
            <Bell size={28} />
            <span className="mt-5 block text-xl font-semibold">交给助手</span>
            <span className="mt-2 block text-base text-violet-100/70">用一句话开始</span>
          </Link>
        </div>
      )}

      <div className="mt-5 grid gap-5 lg:mt-8 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className={`rounded-3xl border border-white/10 bg-slate-900 p-5 sm:p-5 ${timeline.length === 0 ? "hidden lg:block" : ""}`}>
          <div className="flex items-center justify-between gap-3">
            <h3 className="flex items-center gap-2 font-semibold"><CalendarClock size={19} className="text-cyan-300" />今日时间线</h3>
            <span className="text-xs text-slate-500">{timeline.length} 项安排</span>
          </div>
          <div className="mt-5 space-y-1">
            {timeline.length === 0 && <p className="py-7 text-center text-base text-slate-500 sm:py-8">时间线是空的，留一点时间给自己吧。</p>}
            {timeline.map((item) => (
              <article key={`${item.kind}-${item.id}`} className="grid grid-cols-[92px_12px_minmax(0,1fr)] gap-3 py-3">
                <time className="text-sm text-slate-400">
                  {formatTimeInUserTimezone(item.startAt, data.timezone)}
                  <span className="block text-xs text-slate-600">{formatTimeInUserTimezone(item.endAt, data.timezone)}</span>
                </time>
                <span className={`mt-1 size-3 rounded-full ${item.kind === "event" ? "bg-cyan-400" : "bg-violet-400"}`} />
                <div>
                  <h4 className="font-medium text-slate-100">{item.title}</h4>
                  <p className="mt-1 text-xs text-slate-500">{item.kind === "event" ? "日程" : "计划任务"} · {item.detail}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
        <div className="hidden space-y-5 lg:block">
          <NextEventCard event={data.next_event} minutes={data.minutes_until_next_event} timezone={data.timezone} />
          <section className={`rounded-2xl border p-5 ${data.conflicts.length ? "border-red-400/30 bg-red-400/10" : "border-emerald-400/20 bg-emerald-400/5"}`}>
            <div className="flex items-center gap-2">
              {data.conflicts.length ? <AlertTriangle size={19} className="text-red-300" /> : <CheckCircle2 size={19} className="text-emerald-300" />}
              <h3 className="font-semibold">时间冲突</h3>
            </div>
            {data.conflicts.length === 0 ? (
              <p className="mt-3 text-sm text-slate-400">今日安排没有检测到冲突。</p>
            ) : (
              <div className="mt-3 space-y-3">
                {data.conflicts.map((conflict, index) => (
                  <p key={`${conflict.first.id}-${conflict.second.id}-${index}`} className="text-sm text-red-100">
                    {conflict.first.title} 与 {conflict.second.title}
                    <span className="mt-1 block text-xs text-red-200/70">
                      重叠 {formatTimeInUserTimezone(conflict.overlap_start_at, data.timezone)}–{formatTimeInUserTimezone(conflict.overlap_end_at, data.timezone)}
                    </span>
                  </p>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      <div className="mt-5 hidden gap-5 lg:grid lg:grid-cols-3">
        <TaskList title="今日计划任务" tasks={data.planned_tasks} timezone={data.timezone} tone="cyan" onComplete={complete} completing={completeTask.isPending} />
        <TaskList title="今日截止任务" tasks={data.due_tasks} timezone={data.timezone} tone="amber" onComplete={complete} completing={completeTask.isPending} />
        <TaskList title="已逾期任务" tasks={data.overdue_tasks} timezone={data.timezone} tone="red" onComplete={complete} completing={completeTask.isPending} />
      </div>

      {(data.planned_tasks.length > 0 || data.due_tasks.length > 0 || data.overdue_tasks.length > 0) && (
        <section className="mt-5 rounded-2xl border border-white/10 bg-slate-900 p-4 lg:hidden">
          <h3 className="font-semibold text-white">待处理任务</h3>
          <div className="mt-3 space-y-2">
            {[...data.planned_tasks, ...data.due_tasks, ...data.overdue_tasks].slice(0, 4).map((task) => (
              <article key={task.id} className="flex items-center justify-between gap-3 rounded-xl bg-slate-950/60 px-3 py-3">
                <div className="min-w-0"><p className="truncate text-sm font-medium text-slate-100">{task.title}</p><p className="mt-1 text-xs text-slate-500">{task.project || "任务"}</p></div>
                <button type="button" aria-label={`完成任务：${task.title}`} disabled={completeTask.isPending} onClick={() => complete(task.id)} className="shrink-0 rounded-lg p-2 text-emerald-300 hover:bg-emerald-400/10 disabled:opacity-50"><CircleCheck size={19} /></button>
              </article>
            ))}
          </div>
        </section>
      )}

      {data.conflicts.length > 0 && (
        <section className="mt-5 rounded-2xl border border-red-400/30 bg-red-400/10 p-4 lg:hidden">
          <div className="flex items-center gap-2 font-semibold text-red-100"><AlertTriangle size={18} className="text-red-300" />发现 {data.conflicts.length} 个时间冲突</div>
        </section>
      )}

      {data.pending_reminders.length > 0 && (
        <section className="mt-5 rounded-2xl border border-violet-300/15 bg-slate-900 p-4 lg:hidden">
          <div className="flex items-center justify-between gap-3">
            <h3 className="flex items-center gap-2 font-semibold text-white"><Bell size={18} className="text-violet-300" />待处理提醒</h3>
            <span className="text-xs text-slate-500">{data.pending_reminders.length} 项</span>
          </div>
          <div className="mt-3 space-y-2">
            {data.pending_reminders.slice(0, 3).map((reminder) => (
              <article key={reminder.id} className="rounded-xl bg-slate-950/60 px-3 py-3">
                <p className="text-sm font-medium text-slate-100">{reminder.title}</p>
                <p className="mt-1 text-xs text-slate-500">{formatTimeInUserTimezone(reminder.trigger_at, data.timezone)}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="mt-5 hidden rounded-2xl border border-white/10 bg-slate-900 p-5 lg:block">
        <div className="flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 font-semibold"><Bell size={18} className="text-violet-300" />待处理提醒</h3>
          <span className="text-xs text-slate-500">{data.pending_reminders.length} 项</span>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.pending_reminders.length === 0 && <p className="text-sm text-slate-500">今天没有待处理提醒</p>}
          {data.pending_reminders.map((reminder) => (
            <article key={reminder.id} className="rounded-xl bg-slate-950/70 p-4">
              <h4 className="font-medium">{reminder.title}</h4>
              <p className="mt-2 text-xs text-slate-500">{formatTimeInUserTimezone(reminder.trigger_at, data.timezone)} · {reminder.status}</p>
            </article>
          ))}
        </div>
      </section>

      {completeTask.isError && (
        <div role="alert" className="fixed bottom-24 right-6 rounded-xl border border-red-400/30 bg-slate-900 p-4 text-sm text-red-200 shadow-xl">
          任务完成失败：{completeTask.error.message}
        </div>
      )}
    </section>
  );
}
