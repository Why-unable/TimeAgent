import {
  BarChart3,
  CircleCheck,
  CirclePlus,
  Clock,
  Filter,
  ListTodo,
  Pause,
  Pencil,
  Play,
  SkipForward,
  Sparkles,
  Tag,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { getTaskTags, type Task } from "../api/tasks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import {
  useDurationRecommendation,
  useRecordDecisionFeedback,
} from "../features/preferences/time-memory-hooks";
import { useFreeTimeRecommendations } from "../features/planning/hooks";
import { filterTasks, type TaskFilter } from "../features/tasks/filters";
import {
  useCompleteTask,
  useRecordTaskExecutionSignal,
  useTaskExecutionSummary,
  useTasks,
} from "../features/tasks/hooks";
import { TaskEditor } from "../features/tasks/task-editor";
import { TaskEmptyState } from "../features/tasks/task-empty-state";
import { ScheduleWorkspaceTabs } from "../features/workspace/schedule-workspace-tabs";
import { formatInUserTimezone } from "../utils/datetime";
import { isNativePlatform } from "../platform";
import { Button, PageHeader } from "../components/ui/primitives";

const primaryFilters: { id: TaskFilter; label: string }[] = [
  { id: "inbox", label: "收件箱" },
  { id: "today", label: "今日任务" },
  { id: "upcoming", label: "即将到期" },
];
const overflowFilters: { id: TaskFilter; label: string }[] = [
  { id: "overdue", label: "已逾期" },
  { id: "planned", label: "已计划" },
  { id: "in_progress", label: "进行中" },
  { id: "completed", label: "已完成" },
  { id: "all", label: "全部" },
];

const priorityLabels = { low: "低", medium: "中", high: "高", urgent: "紧急" } as const;
const priorityStyles = {
  low: "bg-slate-100 text-slate-700",
  medium: "bg-sky-100 text-sky-900",
  high: "bg-amber-100 text-amber-900",
  urgent: "bg-red-100 text-red-800",
} as const;

export function TasksPage() {
  const preference = useCurrentUserPreference();
  const timezone = preference.data?.timezone ?? "Asia/Shanghai";
  const locale = preference.data?.locale ?? "zh-CN";
  const tasks = useTasks();
  const completeMutation = useCompleteTask();
  const executionMutation = useRecordTaskExecutionSignal();
  const [executionTaskId, setExecutionTaskId] = useState<string>();
  const [recommendationTaskId, setRecommendationTaskId] = useState<string>();
  const executionSummary = useTaskExecutionSummary(executionTaskId);
  const durationRecommendation = useDurationRecommendation(recommendationTaskId);
  const durationFeedback = useRecordDecisionFeedback();
  const [filter, setFilter] = useState<TaskFilter>("inbox");
  const [editingTask, setEditingTask] = useState<Task>();
  const [creating, setCreating] = useState(false);
  const [recommendationRequested, setRecommendationRequested] = useState(false);
  const [completionAnnouncement, setCompletionAnnouncement] = useState("");
  const filterGroupRef = useRef<HTMLDivElement>(null);
  const [desktopLayout, setDesktopLayout] = useState(
    () => typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(min-width: 1024px)").matches
      : false,
  );
  const recommendationRange = useMemo(() => {
    const start = new Date();
    const end = new Date(start.getTime() + 7 * 24 * 60 * 60 * 1000);
    return { range_start: start.toISOString(), range_end: end.toISOString(), duration_minutes: 30, max_results: 6 };
  }, []);
  const recommendations = useFreeTimeRecommendations(recommendationRange, recommendationRequested);
  const visibleTasks = useMemo(
    () => filterTasks(tasks.data ?? [], filter, timezone),
    [filter, tasks.data, timezone],
  );
  const groupedTasks = useMemo(() => {
    const groups = new Map<string, Task[]>();
    visibleTasks.forEach((task) => {
      const project = task.project?.trim() || "无项目";
      groups.set(project, [...(groups.get(project) ?? []), task]);
    });
    return [...groups.entries()];
  }, [visibleTasks]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const media = window.matchMedia("(min-width: 1024px)");
    const sync = () => setDesktopLayout(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  const sendDurationFeedback = (action: "accept" | "too_short" | "too_long" | "disable") => {
    const recommendation = durationRecommendation.data;
    if (!recommendation) return;
    durationFeedback.mutate({
      category: "duration_estimate",
      action,
      value: action === "disable" ? {} : {
        task_id: recommendation.task_id,
        segment: recommendation.segment,
        recommended_minutes: recommendation.recommended_minutes,
      },
      idempotency_key: `${isNativePlatform() ? "android" : "web"}-${action}-${recommendation.task_id}-${Date.now()}`,
      source: isNativePlatform() ? "android" : "web",
    });
  };

  return (
    <section className="mx-auto max-w-6xl">
      <ScheduleWorkspaceTabs />
      <PageHeader
        className="mt-4 lg:mt-7"
        icon={<ListTodo className="text-teal-600" size={25} />}
        title="任务"
        description="明确区分截止时间与计划执行区间。"
        actions={(
          <Button onClick={() => setCreating(true)} size="lg" className="w-full font-semibold lg:w-auto">
            <CirclePlus size={19} />
            新建任务
          </Button>
        )}
      />

      <div ref={filterGroupRef} tabIndex={-1} className="mt-5 rounded-xl outline-none focus-visible:outline-2 focus-visible:outline-teal-700" role="group" aria-label="任务筛选">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {primaryFilters.map((item) => (
            <button
              type="button"
              key={item.id}
              aria-pressed={filter === item.id}
              onClick={() => setFilter(item.id)}
              className={`min-h-11 shrink-0 rounded-full border px-4 py-2 text-sm font-medium transition ${
                filter === item.id
                  ? "border-teal-800 bg-teal-800 text-white ring-2 ring-teal-800 ring-offset-2 mobile-on-brand"
                  : "border-slate-300 bg-white text-slate-700 hover:border-teal-700"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <details className="mt-1">
          <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-full border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:border-teal-700">
            <Filter size={14} />
            更多筛选
            {overflowFilters.some((item) => item.id === filter) && (
              <span className="rounded-full bg-teal-50 px-2 py-0.5 text-teal-900">
                {overflowFilters.find((item) => item.id === filter)?.label}
              </span>
            )}
          </summary>
          <div className="mt-2 flex flex-wrap gap-2 rounded-2xl border border-slate-200 bg-white p-3">
            {overflowFilters.map((item) => (
              <button
                type="button"
                key={item.id}
                aria-pressed={filter === item.id}
                onClick={() => setFilter(item.id)}
                className={`min-h-11 rounded-full border px-3 py-2 text-sm transition ${
                  filter === item.id
                    ? "border-teal-800 bg-teal-800 text-white ring-2 ring-teal-800 ring-offset-2 mobile-on-brand"
                    : "border-slate-300 bg-white text-slate-700 hover:border-teal-700"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </details>
      </div>

      {tasks.isPending && <p className="mt-8 text-slate-400">正在加载任务…</p>}
      {tasks.isError && (
        <div role="alert" className="mt-8 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-amber-100">
          无法读取任务，请确认登录状态后重试。
        </div>
      )}
      {completionAnnouncement && <p className="sr-only" role="status" aria-live="polite">{completionAnnouncement}</p>}
      {!tasks.isPending && !tasks.isError && visibleTasks.length === 0 && <TaskEmptyState />}

      <div className="mt-8 space-y-7">
        <details className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-lg text-left">
            <span>
              <span className="block font-medium text-slate-900">查找未来空闲时间</span>
              <span className="mt-1 block text-xs text-slate-600">只查看候选时间，不会自动创建安排</span>
            </span>
            <Filter size={18} className="shrink-0 text-teal-800" />
          </summary>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-medium text-slate-900">未来空闲时间</h3>
              <p className="mt-1 text-xs text-slate-600">按工作时间、日程和已计划任务寻找 30 分钟候选。</p>
            </div>
            <button type="button" onClick={() => setRecommendationRequested(true)} disabled={recommendations.isFetching} className="min-h-11 rounded-lg border border-teal-700 px-3 py-2 text-sm font-medium text-teal-900 hover:bg-teal-50 disabled:opacity-50">
              {recommendations.isFetching ? "查找中…" : "查找候选"}
            </button>
          </div>
          {recommendations.data && (
            <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {recommendations.data.slots.map((slot) => (
                <div key={`${slot.start_at}-${slot.end_at}`} className="rounded-xl bg-slate-50 p-3 text-sm text-slate-800">
                  {formatInUserTimezone(slot.start_at, timezone, locale)} — {formatInUserTimezone(slot.end_at, timezone, locale)}
                </div>
              ))}
              {recommendations.data.slots.length === 0 && <p className="text-sm text-amber-200">未来范围内没有满足约束的候选时间。</p>}
            </div>
          )}
          {recommendations.isError && <p role="alert" className="mt-3 text-xs text-red-200">空闲时间推荐暂时不可用。</p>}
        </details>
        {groupedTasks.map(([project, projectTasks]) => (
          <section key={project}>
            <div className="mb-3 flex items-center gap-3">
              <h3 className="font-medium text-slate-200">{project}</h3>
              <span className="text-xs text-slate-500">{projectTasks.length} 项</span>
            </div>
            <div className="space-y-3">
              {projectTasks.map((task) => {
                const priority = task.priority ?? "medium";
                const canComplete = task.status === "pending" || task.status === "in_progress";
                return (
              <article key={task.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0 w-full flex-1 sm:w-auto">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className={`min-w-0 break-words text-base leading-snug font-medium ${task.status === "completed" ? "text-slate-500 line-through" : "text-slate-900"}`}>
                            {task.title}
                          </h4>
                          <span className={`rounded-full px-2 py-1 text-xs font-medium ${priorityStyles[priority]}`}>
                            {priorityLabels[priority]}优先级
                          </span>
                          {task.status === "in_progress" && (
                            <span className="rounded-full bg-violet-100 px-2 py-1 text-xs font-medium text-violet-800">进行中</span>
                          )}
                        </div>
                        {task.description && <p className="mt-2 text-sm text-slate-700">{task.description}</p>}
                        <div className="mt-3 flex flex-wrap gap-2 text-xs">
                          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-950">
                            <span className="mr-1 text-[11px] font-medium text-amber-900">截止时间</span>
                            {task.due_at
                              ? formatInUserTimezone(task.due_at, timezone, locale)
                              : "未设置"}
                          </div>
                          <div className="rounded-lg border border-teal-100 bg-teal-50 px-3 py-2 text-teal-950">
                            <span className="mr-1 text-[11px] font-medium text-teal-900">计划执行时间</span>
                            {task.planned_start_at && task.planned_end_at
                              ? `${formatInUserTimezone(task.planned_start_at, timezone, locale)} — ${formatInUserTimezone(task.planned_end_at, timezone, locale)}`
                              : "未计划"}
                          </div>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
                          {task.estimated_minutes && (
                            <span className="inline-flex items-center gap-1"><Clock size={13} />预计 {task.estimated_minutes} 分钟</span>
                          )}
                          {getTaskTags(task).map((tag) => (
                            <span key={tag} className="inline-flex items-center gap-1"><Tag size={12} />{tag}</span>
                          ))}
                        </div>
                      </div>
                      <div className="mt-4 flex w-full flex-wrap items-center gap-2 sm:w-auto">
                        {task.status === "pending" && (
                          <button
                            type="button"
                            aria-label={`开始任务：${task.title}`}
                            disabled={executionMutation.isPending}
                            onClick={() => executionMutation.mutate({ taskId: task.id, signalType: "started" })}
                            className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50 mobile-on-brand"
                          ><Play size={17} />开始</button>
                        )}
                        {task.status === "in_progress" && (
                          <button
                            type="button"
                            aria-label={`暂停任务：${task.title}`}
                            disabled={executionMutation.isPending}
                            onClick={() => executionMutation.mutate({ taskId: task.id, signalType: "paused" })}
                            className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50 mobile-on-brand"
                          ><Pause size={17} />暂停</button>
                        )}
                        {canComplete && (
                          <button
                            type="button"
                            aria-label={`完成任务：${task.title}`}
                            disabled={completeMutation.isPending}
                            onClick={() => completeMutation.mutate(task.id, { onSuccess: () => {
                              setCompletionAnnouncement(`已完成任务：${task.title}`);
                              filterGroupRef.current?.focus();
                            } })}
                            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-emerald-700 bg-white px-4 text-sm font-semibold text-emerald-900 hover:bg-emerald-50 disabled:opacity-50"
                          ><CircleCheck size={17} />完成</button>
                        )}
                        {!desktopLayout && <details className="relative w-full">
                          <summary className="inline-flex min-h-11 cursor-pointer list-none items-center rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700">更多操作</summary>
                          <div className="mt-2 flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2">
                            {canComplete && <button type="button" aria-label={`跳过任务：${task.title}`} disabled={executionMutation.isPending} onClick={() => executionMutation.mutate({ taskId: task.id, signalType: "skipped" })} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-800 disabled:opacity-50"><SkipForward size={16} />跳过</button>}
                            <button type="button" aria-label={`编辑任务：${task.title}`} onClick={() => setEditingTask(task)} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-800"><Pencil size={16} />编辑</button>
                            <button type="button" aria-label={`查看执行摘要：${task.title}`} onClick={() => setExecutionTaskId((current) => current === task.id ? undefined : task.id)} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-800"><BarChart3 size={16} />执行摘要</button>
                            <button type="button" aria-label={`查看估时建议：${task.title}`} onClick={() => setRecommendationTaskId((current) => current === task.id ? undefined : task.id)} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-800"><Sparkles size={16} />估时建议</button>
                          </div>
                        </details>}
                        {desktopLayout && <div className="flex flex-wrap gap-1">
                          {canComplete && <button type="button" aria-label={`跳过任务：${task.title}`} disabled={executionMutation.isPending} onClick={() => executionMutation.mutate({ taskId: task.id, signalType: "skipped" })} className="grid size-11 shrink-0 place-items-center rounded-xl text-slate-600 hover:bg-slate-100 disabled:opacity-50"><SkipForward size={19} /></button>}
                          <button type="button" aria-label={`编辑任务：${task.title}`} onClick={() => setEditingTask(task)} className="grid size-11 shrink-0 place-items-center rounded-xl text-slate-600 hover:bg-slate-100"><Pencil size={18} /></button>
                          <button type="button" aria-label={`查看执行摘要：${task.title}`} onClick={() => setExecutionTaskId((current) => current === task.id ? undefined : task.id)} className="grid size-11 shrink-0 place-items-center rounded-xl text-slate-600 hover:bg-slate-100"><BarChart3 size={18} /></button>
                          <button type="button" aria-label={`查看估时建议：${task.title}`} onClick={() => setRecommendationTaskId((current) => current === task.id ? undefined : task.id)} className="grid size-11 shrink-0 place-items-center rounded-xl text-slate-600 hover:bg-slate-100"><Sparkles size={18} /></button>
                        </div>}
                      </div>
                    </div>
                    {executionTaskId === task.id && (
                      <div className="mt-4 rounded-xl border border-white/10 bg-slate-950/50 p-3 text-sm text-slate-300">
                        {executionSummary.isPending && <p>正在读取执行摘要…</p>}
                        {executionSummary.isError && <p className="text-amber-200">暂时无法读取执行摘要。</p>}
                        {executionSummary.data && (
                          <div className="flex flex-wrap gap-x-5 gap-y-2">
                            <span>已记录 {executionSummary.data.signal_count} 次动作</span>
                            {executionSummary.data.evidence_status === "no_execution_evidence" ? (
                              <span className="text-amber-200">暂无执行证据，无法比较计划与实际。</span>
                            ) : (
                              <span>实际投入 {Math.round(executionSummary.data.active_seconds / 60)} 分钟</span>
                            )}
                            {executionSummary.data.variance_vs_plan_seconds !== null && (
                              <span>
                                相对计划块 {Math.round(executionSummary.data.variance_vs_plan_seconds / 60)} 分钟
                              </span>
                            )}
                            {executionSummary.data.variance_vs_estimate_seconds !== null && (
                              <span>
                                相对估时 {Math.round(executionSummary.data.variance_vs_estimate_seconds / 60)} 分钟
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                    {recommendationTaskId === task.id && (
                      <div className="mt-4 rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-4 text-sm">
                        {durationRecommendation.isPending && <p className="text-slate-400">正在读取估时建议…</p>}
                        {durationRecommendation.isError && <p className="text-amber-200">估时建议暂时不可用。</p>}
                        {durationRecommendation.data && (
                          <div className="space-y-3">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <p className="font-medium text-cyan-100">
                                建议预留 {durationRecommendation.data.recommended_minutes} 分钟
                              </p>
                              <span className="text-xs text-slate-400">
                                {durationRecommendation.data.sample_count} 个样本 · 置信度 {Math.round(durationRecommendation.data.confidence * 100)}%
                              </span>
                            </div>
                            <p className="text-xs leading-5 text-slate-400">
                              {durationRecommendation.data.evidence.join("；")}
                            </p>
                            <p className="text-xs leading-5 text-slate-500">
                              {durationRecommendation.data.classification.category === "unclassified"
                                ? "未使用文本分类"
                                : `任务类型 ${durationRecommendation.data.classification.category} · 分类置信度 ${Math.round(durationRecommendation.data.classification.confidence * 100)}%`}
                              {` · ${durationRecommendation.data.decay_half_life_days} 天半衰期 · 建议有效至 ${new Date(durationRecommendation.data.expires_at).toLocaleDateString()}`}
                            </p>
                            <div className="flex flex-wrap gap-2">
                              <button type="button" disabled={durationFeedback.isPending} onClick={() => sendDurationFeedback("accept")} className="min-h-11 rounded-lg border border-emerald-700 px-3 py-2 text-sm font-medium text-emerald-900 disabled:opacity-50">建议准确</button>
                              <button type="button" disabled={durationFeedback.isPending} onClick={() => sendDurationFeedback("too_short")} className="min-h-11 rounded-lg border border-amber-700 px-3 py-2 text-sm font-medium text-amber-950 disabled:opacity-50">太短</button>
                              <button type="button" disabled={durationFeedback.isPending} onClick={() => sendDurationFeedback("too_long")} className="min-h-11 rounded-lg border border-sky-700 px-3 py-2 text-sm font-medium text-sky-950 disabled:opacity-50">太长</button>
                              <button type="button" disabled={durationFeedback.isPending} onClick={() => sendDurationFeedback("disable")} className="min-h-11 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 disabled:opacity-50">关闭此类建议</button>
                            </div>
                            {durationFeedback.isSuccess && <p role="status" className="text-xs text-emerald-200">估时反馈已记录。</p>}
                            {durationFeedback.isError && <p role="alert" className="text-xs text-red-200">估时反馈保存失败。</p>}
                          </div>
                        )}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      {completeMutation.isError && (
        <div role="alert" className="fixed bottom-24 right-6 rounded-xl border border-red-400/30 bg-slate-900 p-4 text-sm text-red-200 shadow-xl">
          {completeMutation.error.message}
        </div>
      )}
      {executionMutation.isError && (
        <div role="alert" className="fixed bottom-24 right-6 rounded-xl border border-red-400/30 bg-slate-900 p-4 text-sm text-red-200 shadow-xl">
          {executionMutation.error.message}
        </div>
      )}
      {creating && <TaskEditor timezone={timezone} onClose={() => setCreating(false)} />}
      {editingTask && (
        <TaskEditor
          key={editingTask.id}
          task={editingTask}
          timezone={timezone}
          onClose={() => setEditingTask(undefined)}
        />
      )}
    </section>
  );
}
