import {
  AlertTriangle,
  ArrowRight,
  Bell,
  CheckCircle2,
  CircleCheck,
  Clock3,
  Flag,
  Ban,
  Timer,
  MessageSquare,
  Plus,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import type { InteractionArtifact } from "../api/interactions";
import { ensureInteraction, listPendingInteractions } from "../api/interactions";
import type { CalendarEvent } from "../api/events";
import type { Task } from "../api/tasks";
import type { TodaySummary } from "../api/today";
import { useActOnTemporalInsight, useTemporalInsights } from "../features/insights/hooks";
import { MobileSectionHeader } from "../components/mobile/mobile-section-header";
import { DayClosing } from "../components/today/day-closing";
import { MorningBrief } from "../components/today/morning-brief";
import { TodayExecutionSurface } from "../components/today/execution-surface";
import {
  formatCountdown,
  getNextEventLabel,
  getPendingTasks,
  getTimeline,
  type TimelineEntry,
} from "../features/today/derive";
import { useCompleteTodayTask, useTodaySummary } from "../features/today/hooks";
import { interactionComponentRegistry } from "../components/planning/interaction-component-registry";
import { useRecordTaskExecutionSignal } from "../features/tasks/hooks";
import {
  formatDateKey,
  formatInUserTimezone,
  formatTimeInUserTimezone,
} from "../utils/datetime";
import { PageHeader } from "../components/ui/primitives";

const COMPLETION_FEEDBACK_RETRY_KEY = "timeagent.completion-feedback-retry.v1";

function readCompletionFeedbackRetryIds(): string[] {
  try {
    if (typeof window === "undefined") return [];
    const value = window.sessionStorage.getItem(COMPLETION_FEEDBACK_RETRY_KEY);
    const parsed: unknown = value ? JSON.parse(value) : [];
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
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
        className="flex flex-col items-center rounded-xl border border-white/10 bg-slate-900 px-3 py-3"
      >
        <span className="text-2xl font-semibold text-white">{events}</span>
        <span className="mt-1 text-sm text-slate-500">日程</span>
      </Link>
      <Link
        to="/tasks"
        className="flex flex-col items-center rounded-xl border border-white/10 bg-slate-900 px-3 py-3"
      >
        <span className="text-2xl font-semibold text-white">{taskCount}</span>
        <span className="mt-1 text-sm text-slate-500">任务</span>
      </Link>
      <Link
        to="/reminders"
        className="flex flex-col items-center rounded-xl border border-white/10 bg-slate-900 px-3 py-3"
      >
        <span className="text-2xl font-semibold text-white">{reminderCount}</span>
        <span className="mt-1 text-sm text-slate-500">提醒</span>
      </Link>
    </div>
  );
}

function TodayEmptyQuickAction() {
  return (
    <section className="rounded-2xl border border-white/10 bg-slate-900 p-4 lg:flex lg:items-center lg:justify-between lg:gap-5">
      <div><p className="text-sm font-medium text-slate-200">今天还没有安排</p>
      <p className="mt-1 text-xs text-slate-400">让助理根据你的任务先拟一份计划，再由你决定是否应用。</p></div>
      <Link to="/chat?prompt=帮我安排今天的任务&auto_send=1" className="mt-3 flex min-h-12 items-center justify-center gap-2 rounded-xl bg-cyan-300 px-3 text-sm font-semibold text-slate-950 lg:mt-0 lg:min-w-52">
        <MessageSquare size={16} /> 帮我安排今天
      </Link>
      <div className="mt-3 flex justify-center gap-4 text-xs text-slate-400 lg:mt-0">
        <Link to="/calendar" className="inline-flex min-h-10 items-center gap-1"><Plus size={14} />添加日程</Link>
        <Link to="/tasks" className="inline-flex min-h-10 items-center gap-1"><Plus size={14} />添加任务</Link>
      </div>
    </section>
  );
}

export function TodayPage() {
  const queryClient = useQueryClient();
  const [focusInteractionId, setFocusInteractionId] = useState<string | null>(null);
  const [feedbackDismissed, setFeedbackDismissed] = useState(false);
  const [activeCompletionId, setActiveCompletionId] = useState<string | null>(null);
  const [feedbackRetryTaskIds, setFeedbackRetryTaskIds] = useState<string[]>(readCompletionFeedbackRetryIds);
  const retryingFeedbackIds = useRef(new Set<string>());
  const summary = useTodaySummary();
  const completeTask = useCompleteTodayTask();
  const completionInteractions = useQuery({
    queryKey: ["interactions", "task_completion"],
    queryFn: () => listPendingInteractions({ type: "task_completion" }),
    retry: false,
  });
  const startTask = useRecordTaskExecutionSignal();
  const insights = useTemporalInsights();
  const actOnInsight = useActOnTemporalInsight();

  const updateFeedbackRetryQueue = useCallback((update: (current: string[]) => string[]) => {
    setFeedbackRetryTaskIds((current) => {
      const next = update(current);
      try {
        window.sessionStorage.setItem(COMPLETION_FEEDBACK_RETRY_KEY, JSON.stringify(next));
      } catch {
        // The retry remains available in memory for this page even when session storage is unavailable.
      }
      return next;
    });
  }, []);

  const installCompletionInteraction = useCallback((interaction: InteractionArtifact) => {
    if (interaction.status !== "pending") return;
    setFeedbackDismissed(false);
    setActiveCompletionId(interaction.id);
    setFocusInteractionId(interaction.id);
    queryClient.setQueryData<InteractionArtifact[]>(["interactions", "task_completion"], (current = []) => [
      interaction,
      ...current.filter((entry) => entry.id !== interaction.id),
    ]);
  }, [queryClient]);

  const retryCompletionFeedback = useCallback(async (taskId: string) => {
    try {
      const interaction = await ensureInteraction({ type: "task_completion", task_id: taskId });
      installCompletionInteraction(interaction);
      updateFeedbackRetryQueue((current) => current.filter((id) => id !== taskId));
    } catch {
      // Keep the task ID queued so the user can retry without repeating completion.
    }
  }, [installCompletionInteraction, updateFeedbackRetryQueue]);

  useEffect(() => {
    for (const taskId of feedbackRetryTaskIds) {
      if (retryingFeedbackIds.current.has(taskId)) continue;
      retryingFeedbackIds.current.add(taskId);
      void retryCompletionFeedback(taskId).finally(() => retryingFeedbackIds.current.delete(taskId));
    }
  }, [feedbackRetryTaskIds, retryCompletionFeedback]);

  useEffect(() => {
    const rows = completionInteractions.data ?? [];
    if (rows.length === 0) {
      setActiveCompletionId(null);
    } else if (!activeCompletionId || !rows.some((interaction) => interaction.id === activeCompletionId)) {
      setActiveCompletionId(rows[0].id);
    }
  }, [activeCompletionId, completionInteractions.data]);

  useEffect(() => {
    if (focusInteractionId) {
      document.getElementById(`completion-feedback-heading-${focusInteractionId}`)?.focus();
      setFocusInteractionId(null);
    }
  }, [focusInteractionId]);

  useEffect(() => {
    if (feedbackDismissed) {
      document.getElementById("today-completion-feedback-dismissed")?.focus();
    }
  }, [feedbackDismissed]);

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
  const CompletionRenderer = interactionComponentRegistry.task_completion;
  const timeline = getTimeline(data);
  const taskCount = data.unfinished_tasks.length;
  const pendingTasks = getPendingTasks(data);
  const isEmptyDay = timeline.length === 0
    && taskCount === 0
    && data.completed_tasks.length === 0
    && data.pending_reminders.length === 0;
  const complete = async (taskId: string) => {
    try {
      await completeTask.mutateAsync(taskId);
    } catch {
      return;
    }
    try {
      const interaction = await ensureInteraction({ type: "task_completion", task_id: taskId });
      installCompletionInteraction(interaction);
    } catch {
      updateFeedbackRetryQueue((current) => current.includes(taskId) ? current : [...current, taskId]);
    }
  };
  const closeCompletionInteraction = (interaction: InteractionArtifact) => {
    setFocusInteractionId(null);
    setFeedbackDismissed(true);
    const remaining = (completionInteractions.data ?? []).filter((entry) => entry.id !== interaction.id);
    if (remaining.length > 0) {
      setFeedbackDismissed(false);
      setActiveCompletionId(remaining[0].id);
      setFocusInteractionId(remaining[0].id);
    } else {
      setActiveCompletionId(null);
    }
    queryClient.setQueryData<InteractionArtifact[]>(["interactions", "task_completion"], (current = []) =>
      current.filter((entry) => entry.id !== interaction.id),
    );
    void queryClient.invalidateQueries({ queryKey: ["interactions", "task_completion"] });
  };

  return (
    <section className="mx-auto max-w-6xl">
      {/* Shared header (mobile: MobilePageHeader; desktop: same heading in a flex row) */}
      <PageHeader
        icon={<Clock3 className="text-teal-600" size={25} />}
        title="今天"
        description={(
          <>
            {formatDateKey(data.date)}
            <span className="hidden lg:inline"> · {data.timezone}</span>
          </>
        )}
        actions={(
          <div className="hidden gap-2 sm:gap-3 lg:flex">
            <Link to="/calendar" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm font-medium text-slate-200 hover:border-cyan-300/30 sm:px-4">
              日程 <ArrowRight size={15} />
            </Link>
            <Link to="/tasks" className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm font-medium text-slate-200 hover:border-cyan-300/30 sm:px-4">
              任务 <ArrowRight size={15} />
            </Link>
          </div>
        )}
      />

      <MorningBrief targetDate={data.date} />

      {/* Mobile rhythm card */}
      <div className="mt-5 lg:hidden">
        <MobileRhythmCard data={data} timeline={timeline} taskCount={taskCount} />
      </div>

      {feedbackRetryTaskIds.length > 0 && (
        <div role="status" className="mt-3 rounded-lg border border-amber-300/20 bg-amber-300/5 p-3 text-sm text-amber-100">
          完成记录已保存，但反馈卡暂时不可用。{feedbackRetryTaskIds.length > 1 ? `还有 ${feedbackRetryTaskIds.length} 项可以恢复。` : "可以重试显示反馈。"}
          <button type="button" onClick={() => void Promise.all(feedbackRetryTaskIds.map(retryCompletionFeedback))} className="ml-2 min-h-10 underline">重试</button>
        </div>
      )}
      {completionInteractions.data?.filter((interaction) => interaction.id === activeCompletionId).map((interaction) => (
        <CompletionRenderer
          key={interaction.id}
          interaction={interaction}
          autoFocus={focusInteractionId === interaction.id}
          onClose={closeCompletionInteraction}
        />
      ))}
      {(completionInteractions.data?.length ?? 0) > 1 && (
        <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
          尚有 {completionInteractions.data!.length} 项可选反馈。
          <button type="button" onClick={() => {
            const rows = completionInteractions.data ?? [];
            if (rows.length < 2) return;
            const index = rows.findIndex((entry) => entry.id === activeCompletionId);
            const next = rows[(index + 1) % rows.length];
            setFeedbackDismissed(false);
            setActiveCompletionId(next.id);
            setFocusInteractionId(next.id);
          }} className="min-h-10 underline">查看下一项</button>
        </p>
      )}
      {feedbackDismissed && <p id="today-completion-feedback-dismissed" tabIndex={-1} role="status" className="mt-3 rounded-lg border border-emerald-300/20 bg-emerald-300/5 p-3 text-sm text-emerald-100">任务已完成，可选反馈已关闭。</p>}

      {/* Mobile stats row (own block per §7.3) */}
      <div className="mt-4 lg:hidden">
        <MobileStatsRow
          events={data.events.length}
          taskCount={taskCount}
          reminderCount={data.pending_reminders.length}
        />
      </div>

      {isEmptyDay && (
        <div className="mt-4">
          <TodayEmptyQuickAction />
        </div>
      )}

      {/* Mobile timeline */}
      <div className="mt-5 lg:hidden">
        <TodayExecutionSurface
          now={data.execution_now}
          next={data.execution_next}
          later={data.execution_later}
          timezone={data.timezone}
          onComplete={complete}
          onStart={(taskId) => startTask.mutate({ taskId, signalType: "started" })}
          busy={completeTask.isPending || startTask.isPending}
        />
      </div>

      {/* Desktop timeline + right column */}
      <div className="mt-5 hidden gap-5 lg:mt-8 lg:grid lg:grid-cols-[minmax(0,1fr)_340px]">
        <TodayExecutionSurface
          now={data.execution_now}
          next={data.execution_next}
          later={data.execution_later}
          timezone={data.timezone}
          onComplete={complete}
          onStart={(taskId) => startTask.mutate({ taskId, signalType: "started" })}
          busy={completeTask.isPending || startTask.isPending}
        />
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

      {insights.data && insights.data.length > 0 && (
        <section className="mt-5 rounded-2xl border border-amber-300/20 bg-amber-300/5 p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold text-amber-100">需要留意</h3>
              <p className="mt-1 text-xs text-slate-400">只展示有确定事实依据、仍未过期的时间风险。</p>
            </div>
            <span className="text-xs text-slate-500">{insights.data.length} 条</span>
          </div>
          <div className="mt-4 space-y-3">
            {insights.data.slice(0, 3).map((insight) => (
              <article key={insight.id} className="rounded-xl bg-slate-950/50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h4 className="font-medium text-slate-100">{insight.title}</h4>
                    <p className="mt-1 text-sm leading-6 text-slate-300">{insight.summary}</p>
                    <p className="mt-2 text-xs text-slate-500">依据：{String((insight.evidence as { due_at?: unknown }).due_at ?? "任务截止时间")}</p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      title="稍后提醒"
                      aria-label="稍后提醒"
                      disabled={actOnInsight.isPending}
                      onClick={() => actOnInsight.mutate({ insightId: insight.id, input: { action: "snooze", disable_kind: false } })}
                      className="rounded-lg p-2 text-amber-200 hover:bg-amber-300/10 disabled:opacity-50"
                    >
                      <Clock3 size={17} />
                    </button>
                    <button
                      type="button"
                      title="关闭此条"
                      aria-label="关闭此条"
                      disabled={actOnInsight.isPending}
                      onClick={() => actOnInsight.mutate({ insightId: insight.id, input: { action: "dismiss", disable_kind: false } })}
                      className="rounded-lg p-2 text-slate-400 hover:bg-white/10 disabled:opacity-50"
                    >
                      <CheckCircle2 size={17} />
                    </button>
                    <button
                      type="button"
                      title="标记为不准确"
                      aria-label="标记为不准确"
                      disabled={actOnInsight.isPending}
                      onClick={() => actOnInsight.mutate({ insightId: insight.id, input: { action: "false_positive", disable_kind: false } })}
                      className="rounded-lg p-2 text-rose-300 hover:bg-rose-300/10 disabled:opacity-50"
                    >
                      <Flag size={17} />
                    </button>
                    <button
                      type="button"
                      title="关闭此类洞察"
                      aria-label="关闭此类洞察"
                      disabled={actOnInsight.isPending}
                      onClick={() => actOnInsight.mutate({ insightId: insight.id, input: { action: "false_positive", disable_kind: true } })}
                      className="rounded-lg p-2 text-slate-400 hover:bg-white/10 disabled:opacity-50"
                    >
                      <Ban size={17} />
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

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
                  className="min-h-11 min-w-11 shrink-0 rounded-lg p-2 text-emerald-300 hover:bg-emerald-400/10 disabled:opacity-50"
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

      <DayClosing
        date={data.date}
        timezone={data.timezone}
        unfinishedTasks={data.unfinished_tasks}
        completedTasks={data.completed_tasks}
      />

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
