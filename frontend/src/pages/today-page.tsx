import {
  AlertTriangle,
  ArrowRight,
  Bell,
  CheckCircle2,
  Clock3,
  Timer,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import type { InteractionArtifact } from "../api/interactions";
import { ensureInteraction, listPendingInteractions } from "../api/interactions";
import type { CalendarEvent } from "../api/events";
import { useActOnTemporalInsight, useTemporalInsights } from "../features/insights/hooks";
import { MobileSectionHeader } from "../components/mobile/mobile-section-header";
import { DayClosing } from "../components/today/day-closing";
import { MorningBrief } from "../components/today/morning-brief";
import { MobileTodayExecutionSurface, TodayExecutionSurface } from "../components/today/execution-surface";
import { Drawer } from "../components/overlay/drawer";
import {
  formatCountdown,
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

function TodayTaskProgress({ completed, unfinished }: { completed: number; unfinished: number }) {
  const total = completed + unfinished;
  if (total === 0) return null;
  const progress = Math.round((completed / total) * 100);
  return (
    <section aria-label="今日任务进度" className="border-y border-slate-200 py-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-slate-800">今日进度</h2>
        <span className="text-sm text-slate-700">完成 {completed} / {total} 项任务</span>
      </div>
      <div
        role="progressbar"
        aria-label="今日任务完成比例"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={completed}
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200"
      >
        <span className="block h-full rounded-full bg-teal-700 transition-[width]" style={{ width: `${progress}%` }} />
      </div>
    </section>
  );
}

export function TodayPage() {
  const queryClient = useQueryClient();
  const [focusInteractionId, setFocusInteractionId] = useState<string | null>(null);
  const [activeCompletionId, setActiveCompletionId] = useState<string | null>(null);
  const [feedbackDrawerOpen, setFeedbackDrawerOpen] = useState(false);
  const [completionNotice, setCompletionNotice] = useState<{
    taskId: string;
    title: string;
    state: "completed" | "reopened";
  } | null>(null);
  const [completionNoticeError, setCompletionNoticeError] = useState("");
  const [feedbackRetryTaskIds, setFeedbackRetryTaskIds] = useState<string[]>(readCompletionFeedbackRetryIds);
  const retryingFeedbackIds = useRef(new Set<string>());
  const reopenAttempts = useRef(new Map<string, { occurred_at: string; idempotency_key: string }>());
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

  const installCompletionInteraction = useCallback(async (interaction: InteractionArtifact) => {
    if (interaction.status !== "pending") return;
    await queryClient.cancelQueries({ queryKey: ["interactions", "task_completion"] });
    setActiveCompletionId(interaction.id);
    queryClient.setQueryData<InteractionArtifact[]>(["interactions", "task_completion"], (current = []) => [
      interaction,
      ...current.filter((entry) => entry.id !== interaction.id),
    ]);
  }, [queryClient]);

  const retryCompletionFeedback = useCallback(async (taskId: string) => {
    try {
      const interaction = await ensureInteraction({ type: "task_completion", task_id: taskId });
      await installCompletionInteraction(interaction);
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

  if (summary.isPending) {
    return <p role="status" className="mx-auto flex min-h-24 max-w-6xl items-center text-sm text-slate-600">正在整理今天的安排…</p>;
  }
  if (summary.isError || !summary.data) {
    return (
      <div
        role="alert"
        className="mx-auto max-w-6xl border-y border-amber-300 bg-amber-50 py-4 text-amber-950"
      >
        <p className="text-sm font-medium">无法读取今天的安排。请检查连接后重试。</p>
        <button
          type="button"
          onClick={() => void summary.refetch()}
          className="mt-3 inline-flex min-h-12 items-center justify-center rounded-xl bg-amber-900 px-4 text-sm font-semibold text-white hover:bg-amber-950"
        >
          重试
        </button>
      </div>
    );
  }

  const data = summary.data;
  const CompletionRenderer = interactionComponentRegistry.task_completion;
  const complete = async (taskId: string) => {
    const task = [...data.unfinished_tasks, ...data.completed_tasks].find((entry) => entry.id === taskId);
    try {
      await completeTask.mutateAsync(taskId);
    } catch {
      return;
    }
    try {
      const interaction = await ensureInteraction({ type: "task_completion", task_id: taskId });
      await installCompletionInteraction(interaction);
    } catch {
      updateFeedbackRetryQueue((current) => current.includes(taskId) ? current : [...current, taskId]);
    }
    setCompletionNotice({ taskId, title: task?.title ?? "任务", state: "completed" });
    setCompletionNoticeError("");
  };
  const closeCompletionInteraction = (interaction: InteractionArtifact) => {
    setFocusInteractionId(null);
    setFeedbackDrawerOpen(false);
    const remaining = (completionInteractions.data ?? []).filter((entry) => entry.id !== interaction.id);
    if (remaining.length > 0) {
      setActiveCompletionId(remaining[0].id);
    } else {
      setActiveCompletionId(null);
    }
    queryClient.setQueryData<InteractionArtifact[]>(["interactions", "task_completion"], (current = []) =>
      current.filter((entry) => entry.id !== interaction.id),
    );
    void queryClient.invalidateQueries({ queryKey: ["interactions", "task_completion"] });
  };
  const reopenTask = async (taskId: string) => {
    const attempt = reopenAttempts.current.get(taskId) ?? {
      occurred_at: new Date().toISOString(),
      idempotency_key: globalThis.crypto?.randomUUID?.()
        ?? `reopen-${taskId}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    };
    reopenAttempts.current.set(taskId, attempt);
    setCompletionNoticeError("");
    try {
      await startTask.mutateAsync({ taskId, signalType: "reopened", options: attempt });
      reopenAttempts.current.delete(taskId);
      updateFeedbackRetryQueue((current) => current.filter((id) => id !== taskId));
      const task = [...data.completed_tasks, ...data.unfinished_tasks].find((entry) => entry.id === taskId);
      setCompletionNotice({ taskId, title: task?.title ?? "任务", state: "reopened" });
      setFeedbackDrawerOpen(false);
    } catch (error) {
      setCompletionNoticeError(error instanceof Error ? error.message : "恢复失败，请稍后重试。");
      throw error;
    }
  };
  const pendingCompletionTaskIds = (completionInteractions.data ?? [])
    .filter((interaction) => interaction.status === "pending" && interaction.task_id)
    .map((interaction) => interaction.task_id as string);
  const openCompletionFeedback = async (taskId: string) => {
    let interaction = completionInteractions.data?.find((entry) => entry.task_id === taskId);
    if (!interaction) {
      try {
        interaction = await ensureInteraction({ type: "task_completion", task_id: taskId });
        await installCompletionInteraction(interaction);
        updateFeedbackRetryQueue((current) => current.filter((id) => id !== taskId));
      } catch {
        updateFeedbackRetryQueue((current) => current.includes(taskId) ? current : [...current, taskId]);
        setCompletionNoticeError("反馈暂时无法载入，请重试");
        return;
      }
    }
    setActiveCompletionId(interaction.id);
    setFocusInteractionId(interaction.id);
    setFeedbackDrawerOpen(true);
  };

  return (
    <section className="mx-auto max-w-6xl">
      {/* Shared header (mobile: MobilePageHeader; desktop: same heading in a flex row) */}
      <PageHeader
        icon={<Clock3 className="text-teal-600" size={25} />}
        title="今天"
        description={(
          <>
            {formatDateKey(data.date)} · 时间按 {data.timezone} 显示
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

      <div className="hidden lg:block">
        <MorningBrief targetDate={data.date} />
      </div>

      {feedbackRetryTaskIds.length > 0 && (
        <div role="status" className="mt-3 rounded-lg border border-amber-300/20 bg-amber-300/5 p-3 text-sm text-amber-100">
          完成记录已保存，但反馈卡暂时不可用。{feedbackRetryTaskIds.length > 1 ? `还有 ${feedbackRetryTaskIds.length} 项可以恢复。` : "可以重试显示反馈。"}
          <button type="button" onClick={() => void Promise.all(feedbackRetryTaskIds.map(retryCompletionFeedback))} className="ml-2 min-h-10 underline">重试</button>
        </div>
      )}
      {completionNotice && (
        <div role="status" aria-live="polite" className="fixed inset-x-3 bottom-[calc(env(safe-area-inset-bottom)+5.25rem)] z-40 mx-auto flex max-w-xl flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border border-teal-200 bg-white p-3 text-sm text-slate-800 shadow-xl sm:inset-x-auto sm:bottom-6 sm:right-6 sm:mx-0">
          <CheckCircle2 size={18} className="shrink-0 text-teal-700" aria-hidden="true" />
          <span className="min-w-0 flex-1">{completionNotice.state === "completed" ? `${completionNotice.title}：已完成` : `${completionNotice.title}：已恢复为未完成`}</span>
          {completionNotice.state === "completed" ? (
            <>
              <button
                type="button"
                disabled={startTask.isPending}
                onClick={() => void reopenTask(completionNotice.taskId).catch(() => undefined)}
                className="min-h-10 rounded-lg px-3 font-medium text-teal-800 underline underline-offset-2 disabled:opacity-50"
              >恢复未完成</button>
              {pendingCompletionTaskIds.includes(completionNotice.taskId) && (
                <button type="button" onClick={() => void openCompletionFeedback(completionNotice.taskId)} className="min-h-10 rounded-lg bg-teal-700 px-3 font-semibold text-white">记录反馈</button>
              )}
            </>
          ) : null}
          <button type="button" aria-label="关闭提示" onClick={() => setCompletionNotice(null)} className="min-h-10 min-w-10 rounded-lg text-slate-500 hover:bg-slate-100">×</button>
          {completionNoticeError && <span role="alert" className="basis-full text-xs text-rose-700">操作失败：{completionNoticeError}。可安全重试。</span>}
        </div>
      )}
      {feedbackDrawerOpen && completionInteractions.data?.find((interaction) => interaction.id === activeCompletionId) && (
        <Drawer
          title="任务完成反馈"
          description="这是可选反馈；任务状态已保存，你可以随时关闭。"
          onClose={() => setFeedbackDrawerOpen(false)}
        >
          <CompletionRenderer
            key={activeCompletionId}
            interaction={completionInteractions.data.find((interaction) => interaction.id === activeCompletionId)!}
            autoFocus={focusInteractionId === activeCompletionId}
            onClose={closeCompletionInteraction}
            onUndoCompletion={reopenTask}
          />
          {(completionInteractions.data?.length ?? 0) > 1 && (
            <button type="button" onClick={() => {
              const rows = completionInteractions.data ?? [];
              const index = rows.findIndex((entry) => entry.id === activeCompletionId);
              const next = rows[(index + 1) % rows.length];
              setActiveCompletionId(next.id);
              setFocusInteractionId(next.id);
            }} className="mt-3 min-h-11 rounded-lg px-3 text-sm font-medium text-teal-800 underline">查看下一项反馈（共 {completionInteractions.data.length} 项）</button>
          )}
        </Drawer>
      )}

      <div className="mt-4 lg:hidden">
        <MobileTodayExecutionSurface
          now={data.execution_now}
          next={data.execution_next}
          later={data.execution_later}
          timezone={data.timezone}
          onComplete={complete}
          onStart={(taskId) => startTask.mutate({ taskId, signalType: "started" })}
          busy={completeTask.isPending || startTask.isPending}
        />
      </div>

      <div className="mt-4 lg:hidden">
        <TodayTaskProgress completed={data.completed_tasks.length} unfinished={data.unfinished_tasks.length} />
      </div>

      <details className="group mt-3 border-b border-slate-200 pb-2 lg:hidden">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-slate-700">
          <span>晨间简报</span>
          <span aria-hidden="true" className="text-slate-500 transition-transform group-open:rotate-180">⌄</span>
        </summary>
        <MorningBrief targetDate={data.date} />
      </details>

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
        <section aria-labelledby="today-insights-heading" data-surface="none" className="mt-5 border-y border-slate-200 py-4 lg:rounded-2xl lg:border lg:border-amber-300/20 lg:bg-amber-300/5 lg:p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 id="today-insights-heading" className="font-semibold text-amber-900 lg:text-amber-100">需要留意</h2>
              <p className="mt-1 text-xs text-slate-600 lg:text-slate-400">只展示有确定事实依据、仍未过期的时间风险。</p>
            </div>
            <span className="text-xs text-slate-600 lg:text-slate-500">{insights.data.length} 条</span>
          </div>
          <div className="mt-2 divide-y divide-slate-200 lg:mt-4 lg:space-y-3 lg:divide-y-0">
            {insights.data.slice(0, 3).map((insight) => (
              <article key={insight.id} className="border-l-2 border-amber-500 py-3 pl-3">
                <div className="min-w-0">
                    <h3 className="font-medium text-slate-900 lg:text-slate-100">{insight.title}</h3>
                    <p className="mt-1 text-sm leading-6 text-slate-700 lg:text-slate-300">{insight.summary}</p>
                    <p className="mt-2 text-xs text-slate-600 lg:text-slate-500">
                      {(() => {
                        const evidence = insight.evidence;
                        const dueAt = evidence && typeof evidence === "object" && !Array.isArray(evidence)
                          ? (evidence as { due_at?: unknown }).due_at
                          : undefined;
                        if (typeof dueAt !== "string") return "依据：任务截止时间";
                        try {
                          return `截止：${formatInUserTimezone(dueAt, data.timezone)}`;
                        } catch {
                          return "依据：任务截止时间";
                        }
                      })()}
                    </p>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      aria-label={`稍后提醒：${insight.title}`}
                      disabled={actOnInsight.isPending}
                      onClick={() => actOnInsight.mutate({ insightId: insight.id, input: { action: "snooze", disable_kind: false } })}
                      className="inline-flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm font-medium text-amber-900 hover:bg-amber-50 disabled:opacity-50 lg:text-amber-200 lg:hover:bg-amber-300/10"
                    >
                      <Clock3 size={17} aria-hidden="true" />
                      稍后提醒
                    </button>
                  <details className="min-w-0">
                    <summary className="inline-flex min-h-11 cursor-pointer list-none items-center rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-100 lg:text-slate-300 lg:hover:bg-white/10">
                      更多操作
                    </summary>
                    <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-2 lg:border-white/10">
                      <button
                        type="button"
                        aria-label={`关闭此条：${insight.title}`}
                        disabled={actOnInsight.isPending}
                        onClick={() => actOnInsight.mutate({ insightId: insight.id, input: { action: "dismiss", disable_kind: false } })}
                        className="min-h-11 rounded-lg px-3 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-50 lg:text-slate-300 lg:hover:bg-white/10"
                      >
                        关闭此条
                      </button>
                      <button
                        type="button"
                        aria-label={`标记为不准确：${insight.title}`}
                        disabled={actOnInsight.isPending}
                        onClick={() => actOnInsight.mutate({ insightId: insight.id, input: { action: "false_positive", disable_kind: false } })}
                        className="min-h-11 rounded-lg px-3 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-50 lg:text-rose-300 lg:hover:bg-rose-300/10"
                      >
                        标记为不准确
                      </button>
                      <button
                        type="button"
                        aria-label={`关闭此类洞察：${insight.title}`}
                        disabled={actOnInsight.isPending}
                        onClick={() => actOnInsight.mutate({ insightId: insight.id, input: { action: "false_positive", disable_kind: true } })}
                        className="min-h-11 rounded-lg px-3 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-50 lg:text-slate-300 lg:hover:bg-white/10"
                      >
                        关闭此类洞察
                      </button>
                    </div>
                  </details>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* Mobile conflicts */}
      {data.conflicts.length > 0 && (
        <section role="status" className="mt-5 border-l-2 border-red-600 py-2 pl-3 lg:hidden">
          <div className="flex items-center gap-2 font-semibold text-red-800">
            <AlertTriangle size={18} className="text-red-700" aria-hidden="true" />
            发现 {data.conflicts.length} 个时间冲突
          </div>
        </section>
      )}

      {/* Mobile pending reminders */}
      {data.pending_reminders.length > 0 && (
        <section className="mt-5 border-t border-slate-200 pt-4 lg:hidden">
          <MobileSectionHeader
            icon={<Bell size={18} className="text-violet-800" />}
            title="待处理提醒"
            meta={`${data.pending_reminders.length} 项`}
          />
          <div className="mt-2 divide-y divide-slate-200">
            {data.pending_reminders.slice(0, 3).map((reminder) => (
              <Link
                key={reminder.id}
                to="/reminders"
                className="flex min-h-14 items-center justify-between gap-3 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-base font-medium text-slate-900">{reminder.title}</p>
                  <p className="mt-1 text-xs text-slate-600">
                    {formatTimeInUserTimezone(reminder.trigger_at, data.timezone)}
                  </p>
                </div>
                <ArrowRight size={16} className="shrink-0 text-slate-600" />
              </Link>
            ))}
            {data.pending_reminders.length > 3 && (
              <Link
                to="/reminders"
                className="inline-flex min-h-11 items-center text-sm font-medium text-teal-800"
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
        pendingCompletionTaskIds={pendingCompletionTaskIds}
        onReopenTask={reopenTask}
        onOpenFeedbackTask={(taskId) => void openCompletionFeedback(taskId)}
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
