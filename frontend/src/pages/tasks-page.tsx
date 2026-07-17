import { CircleCheck, CirclePlus, Clock, ListTodo, Pencil, Tag } from "lucide-react";
import { useMemo, useState } from "react";

import { getTaskTags, type Task } from "../api/tasks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import { filterTasks, type TaskFilter } from "../features/tasks/filters";
import { useCompleteTask, useTasks } from "../features/tasks/hooks";
import { TaskEditor } from "../features/tasks/task-editor";
import { formatInUserTimezone } from "../utils/datetime";

const filters: { id: TaskFilter; label: string }[] = [
  { id: "inbox", label: "Inbox" },
  { id: "today", label: "今日任务" },
  { id: "upcoming", label: "即将到期" },
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
  const [filter, setFilter] = useState<TaskFilter>("inbox");
  const [editingTask, setEditingTask] = useState<Task>();
  const [creating, setCreating] = useState(false);
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

  return (
    <section className="mx-auto max-w-6xl">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-cyan-300">Phase 3 · 结构化事务</p>
          <div className="mt-2 flex items-center gap-3">
            <ListTodo className="text-cyan-300" />
            <h2 className="text-3xl font-semibold">任务</h2>
          </div>
          <p className="mt-3 text-slate-400">明确区分截止时间与计划执行区间。</p>
        </div>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-cyan-300 px-5 py-3 font-medium text-slate-950"
        >
          <CirclePlus size={19} />
          新建任务
        </button>
      </div>

      <div className="mt-7 flex gap-2 overflow-x-auto pb-2" aria-label="任务筛选">
        {filters.map((item) => (
          <button
            type="button"
            key={item.id}
            onClick={() => setFilter(item.id)}
            className={`shrink-0 rounded-full px-4 py-2 text-sm transition ${
              filter === item.id
                ? "bg-cyan-300 text-slate-950"
                : "border border-white/10 bg-slate-900 text-slate-300 hover:border-cyan-300/30"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tasks.isPending && <p className="mt-8 text-slate-400">正在加载任务…</p>}
      {tasks.isError && (
        <div role="alert" className="mt-8 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-amber-100">
          无法读取任务，请确认登录状态后重试。
        </div>
      )}
      {!tasks.isPending && !tasks.isError && visibleTasks.length === 0 && (
        <div className="mt-8 rounded-2xl border border-dashed border-white/10 p-12 text-center text-slate-500">
          当前分类暂无任务
        </div>
      )}

      <div className="mt-8 space-y-7">
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
                            <span className="block text-[11px] uppercase tracking-wide text-amber-300/70">截止时间 due_at</span>
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
                      </div>
                    </div>
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
