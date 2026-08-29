import {
  BarChart3,
  CircleCheck,
  CirclePlus,
  Clock,
  ListTodo,
  Pause,
  Pencil,
  Play,
  SkipForward,
  Sparkles,
  Tag,
} from "lucide-react";
import { useMemo, useState } from "react";

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

const primaryFilters: { id: TaskFilter; label: string }[] = [
  { id: "inbox", label: "Inbox" },
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
  low: "bg-slate-400/10 text-slate-300",
  medium: "bg-sky-400/10 text-sky-200",
  high: "bg-amber-400/10 text-amber-200",
  urgent: "bg-red-400/10 text-red-200",
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
      <div className="mt-4 flex flex-col gap-4 lg:mt-2 lg:flex-row lg:flex-wrap lg:items-end lg:justify-between">
        <div className="hidden lg:block">
          <div className="mt-2 flex items-center gap-3">
            <ListTodo className="text-cyan-300" size={31} />
            <h2 className="text-4xl font-semibold">任务</h2>
          </div>
          <p className="mt-4 text-lg text-slate-400">明确区分截止时间与计划执行区间。</p>
        </div>
        <p className="text-base text-slate-400 lg:hidden">明确区分截止时间与计划执行区间。</p>
        {/* Mobile-only heading for tests/accessibility (visually hidden) */}
        <h2 className="sr-only lg:hidden">任务</h2>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="inline-flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-cyan-300 px-6 py-3 text-lg font-semibold text-slate-950 lg:w-auto"
        >
          <CirclePlus size={19} />
          新建任务
        </button>
      </div>

      <div className="mt-6" aria-label="任务筛选">
        <div className="flex gap-3 overflow-x-auto pb-2">
          {primaryFilters.map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => setFilter(item.id)}
              className={`min-h-12 shrink-0 rounded-full px-5 py-3 text-base transition ${
                filter === item.id
                  ? "bg-cyan-300 text-slate-950"
                  : "border border-white/10 bg-slate-900 text-slate-300 hover:border-cyan-300/30"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="mt-2 flex gap-3 overflow-x-auto pb-2">
          {overflowFilters.map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => setFilter(item.id)}
              className={`min-h-12 shrink-0 rounded-full px-4 py-2 text-sm transition ${
                filter === item.id
                  ? "bg-cyan-300 text-slate-950"
                  : "border border-white/10 bg-slate-900 text-slate-400 hover:border-cyan-300/30"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {tasks.isPending && <p className="mt-8 text-slate-400">正在加载任务…</p>}
      {tasks.isError && (
        <div role="alert" className="mt-8 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-amber-100">
          无法读取任务，请确认登录状态后重试。
        </div>
      )}
      {!tasks.isPending && !tasks.isError && visibleTasks.length === 0 && <TaskEmptyState />}

      <div className="mt-8 space-y-7">
        <section className="rounded-2xl border border-cyan-300/20 bg-cyan-300/5 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-medium text-cyan-100">未来空闲时间</h3>
              <p className="mt-1 text-xs text-slate-400">按工作时间、日程和已计划任务寻找 30 分钟候选，不会自动创建安排。</p>
            </div>
            <button type="button" onClick={() => setRecommendationRequested(true)} disabled={recommendations.isFetching} className="rounded-lg border border-cyan-300/30 px-3 py-2 text-xs text-cyan-100 hover:bg-cyan-300/10 disabled:opacity-50">
              {recommendations.isFetching ? "查找中…" : "查找候选"}
            </button>
          </div>
          {recommendations.data && (
            <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {recommendations.data.slots.map((slot) => (
                <div key={`${slot.start_at}-${slot.end_at}`} className="rounded-xl bg-slate-950/50 p-3 text-xs text-slate-300">
                  {formatInUserTimezone(slot.start_at, timezone, locale)} — {formatInUserTimezone(slot.end_at, timezone, locale)}
                </div>
              ))}
              {recommendations.data.slots.length === 0 && <p className="text-sm text-amber-200">未来范围内没有满足约束的候选时间。</p>}
            </div>
          )}
          {recommendations.isError && <p role="alert" className="mt-3 text-xs text-red-200">空闲时间推荐暂时不可用。</p>}
        </section>
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
                  <article key={task.id} className="rounded-2xl border border-white/10 bg-slate-900 p-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className={`font-medium ${task.status === "completed" ? "text-slate-500 line-through" : "text-white"}`}>
                            {task.title}
                          </h4>
                          <span className={`rounded-full px-2 py-1 text-[11px] ${priorityStyles[priority]}`}>
                            {priorityLabels[priority]}优先级
                          </span>
                          {task.status === "in_progress" && (
                            <span className="rounded-full bg-violet-400/10 px-2 py-1 text-[11px] text-violet-200">进行中</span>
                          )}
                        </div>
                        {task.description && <p className="mt-2 text-sm text-slate-400">{task.description}</p>}
                        <div className="mt-4 grid gap-2 text-sm md:grid-cols-2">
                          <div className="rounded-xl bg-amber-300/5 px-3 py-2 text-amber-100">
                            <span className="block text-[11px] uppercase tracking-wide text-amber-300/70">截止时间</span>
                            {task.due_at
                              ? formatInUserTimezone(task.due_at, timezone, locale)
                              : "未设置"}
                          </div>
                          <div className="rounded-xl bg-cyan-300/5 px-3 py-2 text-cyan-100">
                            <span className="block text-[11px] uppercase tracking-wide text-cyan-300/70">计划执行时间</span>
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
                      <div className="flex items-center gap-2">
                        {task.status === "pending" && (
                          <button
                            type="button"
                            aria-label={`开始任务：${task.title}`}
                            disabled={executionMutation.isPending}
                            onClick={() =>
                              executionMutation.mutate({ taskId: task.id, signalType: "started" })
                            }
                            className="rounded-xl p-2 text-cyan-300 hover:bg-cyan-400/10 disabled:opacity-50"
                          >
                            <Play size={19} />
                          </button>
                        )}
                        {task.status === "in_progress" && (
                          <button
                            type="button"
                            aria-label={`暂停任务：${task.title}`}
                            disabled={executionMutation.isPending}
                            onClick={() =>
                              executionMutation.mutate({ taskId: task.id, signalType: "paused" })
                            }
                            className="rounded-xl p-2 text-amber-300 hover:bg-amber-400/10 disabled:opacity-50"
                          >
                            <Pause size={19} />
                          </button>
                        )}
                        {canComplete && (
                          <button
                            type="button"
                            aria-label={`跳过任务：${task.title}`}
                            disabled={executionMutation.isPending}
                            onClick={() =>
                              executionMutation.mutate({ taskId: task.id, signalType: "skipped" })
                            }
                            className="rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-white disabled:opacity-50"
                          >
                            <SkipForward size={19} />
                          </button>
                        )}
                        {canComplete && (
                          <button
                            type="button"
                            aria-label={`完成任务：${task.title}`}
                            disabled={completeMutation.isPending}
                            onClick={() => completeMutation.mutate(task.id)}
                            className="rounded-xl p-2 text-emerald-300 hover:bg-emerald-400/10 disabled:opacity-50"
                          >
                            <CircleCheck size={20} />
                          </button>
                        )}
                        <button
                          type="button"
                          aria-label={`编辑任务：${task.title}`}
                          onClick={() => setEditingTask(task)}
                          className="rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-white"
                        >
                          <Pencil size={18} />
                        </button>
                        <button
                          type="button"
                          aria-label={`查看执行摘要：${task.title}`}
                          onClick={() =>
                            setExecutionTaskId((current) => (current === task.id ? undefined : task.id))
                          }
                          className="rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-white"
                        >
                          <BarChart3 size={18} />
                        </button>
                        <button
                          type="button"
                          aria-label={`查看估时建议：${task.title}`}
                          onClick={() =>
                            setRecommendationTaskId((current) =>
                              current === task.id ? undefined : task.id
                            )
                          }
                          className="rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-cyan-200"
                        >
                          <Sparkles size={18} />
                        </button>
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
                              <button type="button" disabled={durationFeedback.isPending} onClick={() => sendDurationFeedback("accept")} className="rounded-lg border border-emerald-300/30 px-3 py-2 text-xs text-emerald-200 disabled:opacity-50">建议准确</button>
                              <button type="button" disabled={durationFeedback.isPending} onClick={() => sendDurationFeedback("too_short")} className="rounded-lg border border-amber-300/30 px-3 py-2 text-xs text-amber-200 disabled:opacity-50">太短</button>
                              <button type="button" disabled={durationFeedback.isPending} onClick={() => sendDurationFeedback("too_long")} className="rounded-lg border border-sky-300/30 px-3 py-2 text-xs text-sky-200 disabled:opacity-50">太长</button>
                              <button type="button" disabled={durationFeedback.isPending} onClick={() => sendDurationFeedback("disable")} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-400 disabled:opacity-50">关闭此类建议</button>
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
