import {
  AlertTriangle,
  ArrowRight,
  Bell,
  CheckCircle2,
  CircleCheck,
  Clock3,
  Timer,
} from "lucide-react";
import { Link } from "react-router-dom";

import type { CalendarEvent } from "../api/events";
import type { Task } from "../api/tasks";
import type { TodaySummary } from "../api/today";
import { MobileSectionHeader } from "../components/mobile/mobile-section-header";
import {
  countPendingTasks,
  formatCountdown,
  getNextEventLabel,
  getPendingTasks,
  getTimeline,
  type TimelineEntry,
} from "../features/today/derive";
import { TodayTimeline } from "../features/today/today-timeline";
import { useCompleteTodayTask, useTodaySummary } from "../features/today/hooks";
import {
  formatDateKey,
  formatInUserTimezone,
  formatTimeInUserTimezone,
} from "../utils/datetime";

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
          <article
            key={task.id}
            className="flex items-start justify-between gap-3 rounded-xl bg-slate-950/50 p-4"
          >
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

function NextEventCard({
  event,
  minutes,
  timezone,
}: {
  event: CalendarEvent | null;
  minutes: number | null;
  timezone: string;
}) {
  return (
    <section className="rounded-2xl border border-cyan-300/20 bg-gradient-to-br from-cyan-300/10 to-violet-400/5 p-5">
      <div className="flex items-center gap-2 text-sm text-cyan-200">
        <Timer size={17} />
        下一个日程
      </div>
      {event ? (
        <>
          <h3 className="mt-4 text-xl font-semibold">{event.title}</h3>
          <p className="mt-2 text-sm text-slate-300">
            {formatTimeInUserTimezone(event.start_at, timezone)}–
            {formatTimeInUserTimezone(event.end_at, timezone)}
            {event.location ? ` · ${event.location}` : ""}
          </p>
          <p className="mt-5 text-2xl font-semibold text-cyan-200">{formatCountdown(minutes)}</p>
        </>
      ) : (
        <div className="mt-5 flex items-center gap-2 text-slate-400">
          <CheckCircle2 size={20} />
          {formatCountdown(null)}
        </div>
      )}
    </section>
  );
}

function MobileRhythmCard({
  data,
  timeline,
  taskCount,
}: {
  data: TodaySummary;
  timeline: TimelineEntry[];
  taskCount: number;
}) {
  const empty = timeline.length === 0 && taskCount === 0;
  const nextLabel = getNextEventLabel(data);
  return (
    <section className="rounded-[var(--mobile-card-radius)] border border-cyan-300/20 bg-gradient-to-br from-slate-800 to-slate-900 p-6 shadow-[0_24px_55px_-34px_rgba(34,211,238,0.65)] lg:hidden">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-cyan-200">今日节奏</p>
          <h3 className="mt-2 text-[26px] font-semibold leading-tight text-white">
            {empty ? "今天很轻松" : "按自己的节奏来"}
          </h3>
        </div>
        <span className="rounded-full bg-cyan-300/10 px-4 py-2 text-sm font-medium text-cyan-100">
          {timeline.length} 项安排
        </span>
      </div>
      <p className="mt-4 text-base text-slate-400">{nextLabel}</p>
    </section>
  );
}

function MobileStatsRow({
  events,
  taskCount,
  reminderCount,
}: {
  events: number;
  taskCount: number;
  reminderCount: number;
}) {
  return (
    <div className="grid grid-cols-3 gap-3 lg:hidden">
      <Link
        to="/calendar"
        className="flex flex-col items-center rounded-2xl border border-white/10 bg-slate-900 px-3 py-4"
      >
        <span className="text-3xl font-semibold text-white">{events}</span>
        <span className="mt-1 text-sm text-slate-500">日程</span>
      </Link>
      <Link
        to="/tasks"
        className="flex flex-col items-center rounded-2xl border border-white/10 bg-slate-900 px-3 py-4"
      >
        <span className="text-3xl font-semibold text-white">{taskCount}</span>
        <span className="mt-1 text-sm text-slate-500">任务</span>
      </Link>
      <Link
        to="/reminders"
        className="flex flex-col items-center rounded-2xl border border-white/10 bg-slate-900 px-3 py-4"
      >
        <span className="text-3xl font-semibold text-white">{reminderCount}</span>
        <span className="mt-1 text-sm text-slate-500">提醒</span>
      </Link>
    </div>
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
      <div
        role="alert"
        className="mx-auto max-w-6xl rounded-xl border border-amber-400/30 bg-amber-400/10 p-5 text-amber-100"
      >
        无法读取今日工作台，请确认登录状态后重试。
      </div>
    );
  }

  const data = summary.data;
  const timeline = getTimeline(data);
  const taskCount = countPendingTasks(data);
  const pendingTasks = getPendingTasks(data);
  const complete = (taskId: string) => completeTask.mutate(taskId);

  return (
    <section className="mx-auto max-w-6xl">
      {/* Shared header (mobile: MobilePageHeader; desktop: same heading in a flex row) */}
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <div className="flex items-center gap-3">
            <Clock3 className="text-cyan-300" size={30} />
            <h2 className="text-3xl font-semibold lg:text-4xl">今天</h2>
          </div>
          <p className="mt-2 text-base text-slate-400">
            {formatDateKey(data.date)}
            <span className="hidden lg:inline"> · {data.timezone}</span>
          </p>
        </div>
        <div className="hidden gap-2 sm:gap-3 lg:flex">
          <Link
            to="/calendar"
            className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm font-medium text-slate-200 hover:border-cyan-300/30 sm:px-4"
          >
            日历 <ArrowRight size={15} />
          </Link>
          <Link
            to="/tasks"
            className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm font-medium text-slate-200 hover:border-cyan-300/30 sm:px-4"
          >
            任务 <ArrowRight size={15} />
          </Link>
        </div>
      </div>

      {/* Mobile rhythm card */}
      <div className="mt-5 lg:hidden">
        <MobileRhythmCard data={data} timeline={timeline} taskCount={taskCount} />
      </div>

      {/* Mobile stats row (own block per §7.3) */}
      <div className="mt-4 lg:hidden">
        <MobileStatsRow
          events={data.events.length}
          taskCount={taskCount}
          reminderCount={data.pending_reminders.length}
        />
      </div>

      {/* Mobile timeline */}
      <div className="mt-5 lg:hidden">
        <TodayTimeline timeline={timeline} timezone={data.timezone} compact />
      </div>

      {/* Desktop timeline + right column */}
      <div className="mt-5 hidden gap-5 lg:mt-8 lg:grid lg:grid-cols-[minmax(0,1fr)_340px]">
        <TodayTimeline timeline={timeline} timezone={data.timezone} />
        <div className="space-y-5">
          <NextEventCard
            event={data.next_event}
            minutes={data.minutes_until_next_event}
            timezone={data.timezone}
          />
          <section
            className={`rounded-2xl border p-5 ${
              data.conflicts.length
                ? "border-red-400/30 bg-red-400/10"
                : "border-emerald-400/20 bg-emerald-400/5"
            }`}
          >
            <div className="flex items-center gap-2">
              {data.conflicts.length ? (
                <AlertTriangle size={19} className="text-red-300" />
              ) : (
                <CheckCircle2 size={19} className="text-emerald-300" />
              )}
              <h3 className="font-semibold">时间冲突</h3>
            </div>
            {data.conflicts.length === 0 ? (
              <p className="mt-3 text-sm text-slate-400">今日安排没有检测到冲突。</p>
            ) : (
              <div className="mt-3 space-y-3">
                {data.conflicts.map((conflict, index) => (
                  <p
                    key={`${conflict.first.id}-${conflict.second.id}-${index}`}
                    className="text-sm text-red-100"
                  >
                    {conflict.first.title} 与 {conflict.second.title}
                    <span className="mt-1 block text-xs text-red-200/70">
                      重叠 {formatTimeInUserTimezone(conflict.overlap_start_at, data.timezone)}–
                      {formatTimeInUserTimezone(conflict.overlap_end_at, data.timezone)}
                    </span>
                  </p>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      {/* Desktop task columns */}
      <div className="mt-5 hidden gap-5 lg:grid lg:grid-cols-3">
        <TaskList
          title="今日计划任务"
          tasks={data.planned_tasks}
          timezone={data.timezone}
          tone="cyan"
          onComplete={complete}
          completing={completeTask.isPending}
        />
        <TaskList
          title="今日截止任务"
          tasks={data.due_tasks}
          timezone={data.timezone}
          tone="amber"
          onComplete={complete}
          completing={completeTask.isPending}
        />
        <TaskList
          title="已逾期任务"
          tasks={data.overdue_tasks}
          timezone={data.timezone}
          tone="red"
          onComplete={complete}
          completing={completeTask.isPending}
        />
      </div>

      {/* Mobile pending tasks */}
      {pendingTasks.length > 0 && (
        <section className="mt-5 rounded-2xl border border-white/10 bg-slate-900 p-4 lg:hidden">
          <MobileSectionHeader title="待处理任务" meta={`${pendingTasks.length} 项`} />
          <div className="mt-3 space-y-2">
            {pendingTasks.slice(0, 4).map((task) => (
              <article
                key={task.id}
                className="flex items-center justify-between gap-3 rounded-xl bg-slate-950/60 px-3 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-base font-medium text-slate-100">{task.title}</p>
                  <p className="mt-1 text-xs text-slate-500">{task.project || "任务"}</p>
                </div>
                <button
                  type="button"
                  aria-label={`完成任务：${task.title}`}
                  disabled={completeTask.isPending}
                  onClick={() => complete(task.id)}
                  className="shrink-0 rounded-lg p-2 text-emerald-300 hover:bg-emerald-400/10 disabled:opacity-50"
                >
                  <CircleCheck size={19} />
                </button>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* Mobile conflicts */}
      {data.conflicts.length > 0 && (
        <section className="mt-5 rounded-2xl border border-red-400/30 bg-red-400/10 p-4 lg:hidden">
          <div className="flex items-center gap-2 font-semibold text-red-100">
            <AlertTriangle size={18} className="text-red-300" />
            发现 {data.conflicts.length} 个时间冲突
          </div>
        </section>
      )}

      {/* Mobile pending reminders */}
      {data.pending_reminders.length > 0 && (
        <section className="mt-5 rounded-2xl border border-violet-300/15 bg-slate-900 p-4 lg:hidden">
          <MobileSectionHeader
            icon={<Bell size={18} className="text-violet-300" />}
            title="待处理提醒"
            meta={`${data.pending_reminders.length} 项`}
          />
          <div className="mt-3 space-y-2">
            {data.pending_reminders.slice(0, 3).map((reminder) => (
              <Link
                key={reminder.id}
                to="/reminders"
                className="flex items-center justify-between gap-3 rounded-xl bg-slate-950/60 px-3 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-base font-medium text-slate-100">{reminder.title}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {formatTimeInUserTimezone(reminder.trigger_at, data.timezone)}
                  </p>
                </div>
                <ArrowRight size={16} className="shrink-0 text-slate-500" />
              </Link>
            ))}
            {data.pending_reminders.length > 3 && (
              <Link
                to="/reminders"
                className="block w-full rounded-xl border border-white/10 px-3 py-3 text-center text-sm font-medium text-cyan-200"
              >
                查看全部
              </Link>
            )}
          </div>
        </section>
      )}

      {/* Desktop reminders */}
      <section className="mt-5 hidden rounded-2xl border border-white/10 bg-slate-900 p-5 lg:block">
        <div className="flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 font-semibold">
            <Bell size={18} className="text-violet-300" />
            待处理提醒
          </h3>
          <span className="text-xs text-slate-500">{data.pending_reminders.length} 项</span>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.pending_reminders.length === 0 && (
            <p className="text-sm text-slate-500">今天没有待处理提醒</p>
          )}
          {data.pending_reminders.map((reminder) => (
            <article key={reminder.id} className="rounded-xl bg-slate-950/70 p-4">
              <h4 className="font-medium">{reminder.title}</h4>
              <p className="mt-2 text-xs text-slate-500">
                {formatTimeInUserTimezone(reminder.trigger_at, data.timezone)} · {reminder.status}
              </p>
            </article>
          ))}
        </div>
      </section>

      {completeTask.isError && (
        <div
          role="alert"
          className="fixed bottom-24 right-6 rounded-xl border border-red-400/30 bg-slate-900 p-4 text-sm text-red-200 shadow-xl"
        >
          任务完成失败：{completeTask.error.message}
        </div>
      )}
    </section>
  );
}
