import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Check, ChevronDown, Sprout } from "lucide-react";

import type { Task } from "../../api/tasks";
import { getSchedulePlan, type SchedulePlan } from "../../api/planning";
import { useAbandonSchedulePlan, useCreateSchedulePlan } from "../../features/planning/hooks";
import { formatDateKey, toUtcISOString } from "../../utils/datetime";

const TaskEditor = lazy(async () => {
  const module = await import("../../features/tasks/task-editor");
  return { default: module.TaskEditor };
});

type PlanItem = { kind?: string; state?: string; task_id?: string; reason_codes?: string[] };
type SavedClosingState = {
  selectedTaskIds: string[];
  fingerprint: string | null;
  operationId: string | null;
  planId: string | null;
};

function closingStorageKey(date: string, timezone: string) {
  return `time-agent:day-closing:v1:${date}:${timezone}`;
}

function readClosingState(key: string): SavedClosingState | null {
  try {
    const value = window.sessionStorage.getItem(key);
    if (!value) return null;
    const parsed = JSON.parse(value) as Partial<SavedClosingState>;
    if (!Array.isArray(parsed.selectedTaskIds) || !parsed.selectedTaskIds.every((id) => typeof id === "string")) return null;
    return {
      selectedTaskIds: parsed.selectedTaskIds,
      fingerprint: typeof parsed.fingerprint === "string" ? parsed.fingerprint : null,
      operationId: typeof parsed.operationId === "string" ? parsed.operationId : null,
      planId: typeof parsed.planId === "string" ? parsed.planId : null,
    };
  } catch {
    return null;
  }
}

function saveClosingState(key: string, state: SavedClosingState) {
  try {
    window.sessionStorage.setItem(key, JSON.stringify(state));
  } catch {
    // Keep the in-memory operation id when storage is unavailable in a WebView.
  }
}

function createOperationId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (token) => {
    const random = Math.floor(Math.random() * 16);
    return (token === "x" ? random : (random & 0x3) | 0x8).toString(16);
  });
}

function addDateDays(dateKey: string, days: number) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateKey);
  if (!match) throw new Error("Date key must use YYYY-MM-DD");
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function planOutcome(plan: SchedulePlan) {
  const items = Array.isArray(plan.items) ? (plan.items as PlanItem[]) : [];
  const taskItems = items.filter((item) => item.kind !== "plan_evidence");
  return {
    placed: taskItems.filter((item) => item.state === "placed").length,
    unplaced: taskItems.filter((item) => item.state !== "placed"),
  };
}

export function DayClosing({
  date,
  timezone,
  unfinishedTasks,
  completedTasks,
}: {
  date: string;
  timezone: string;
  unfinishedTasks: Task[];
  completedTasks: Task[];
}) {
  const [open, setOpen] = useState(false);
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [createdPlan, setCreatedPlan] = useState<SchedulePlan | null>(null);
  const [draftAbandoned, setDraftAbandoned] = useState(false);
  const [keptUnplaced, setKeptUnplaced] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [taskEditsSaved, setTaskEditsSaved] = useState(false);
  const createPlan = useCreateSchedulePlan();
  const abandonPlan = useAbandonSchedulePlan();
  const operationRef = useRef<{ fingerprint: string; id: string } | null>(null);
  const tomorrow = addDateDays(date, 1);
  const afterTomorrow = addDateDays(date, 2);
  const storageKey = closingStorageKey(date, timezone);
  const availableTaskIds = useRef(new Set(unfinishedTasks.map((task) => task.id)));
  availableTaskIds.current = new Set(unfinishedTasks.map((task) => task.id));
  const selected = new Set(selectedTaskIds);

  useEffect(() => {
    let active = true;
    const saved = readClosingState(storageKey);
    const restoredTaskIds = (saved?.selectedTaskIds ?? []).filter((id) => availableTaskIds.current.has(id));
    setSelectedTaskIds(restoredTaskIds);
    setCreatedPlan(null);
    setDraftAbandoned(false);
    setKeptUnplaced(false);
    setTaskEditsSaved(false);
    setEditingTask(null);
    operationRef.current = saved?.operationId && saved.fingerprint
      ? { fingerprint: saved.fingerprint, id: saved.operationId }
      : null;
    setOpen(restoredTaskIds.length > 0 || Boolean(saved?.planId));
    if (saved?.planId) {
      void getSchedulePlan(saved.planId).then((plan) => {
        if (!active) return;
        if (plan.status === "draft") {
          setCreatedPlan(plan);
        } else {
          operationRef.current = null;
          saveClosingState(storageKey, {
            selectedTaskIds: restoredTaskIds,
            fingerprint: null,
            operationId: null,
            planId: null,
          });
        }
      }).catch(() => {
        // Keep the selection and operation id so retry remains idempotent.
      });
    }
    return () => { active = false; };
  }, [storageKey]);

  const toggleTask = (taskId: string) => {
    const nextSelection = selectedTaskIds.includes(taskId)
      ? selectedTaskIds.filter((id) => id !== taskId)
      : [...selectedTaskIds, taskId];
    setSelectedTaskIds(nextSelection);
    saveClosingState(storageKey, {
      selectedTaskIds: nextSelection,
      fingerprint: null,
      operationId: null,
      planId: null,
    });
    setCreatedPlan(null);
    setDraftAbandoned(false);
    setKeptUnplaced(false);
    setTaskEditsSaved(false);
    operationRef.current = null;
  };

  const createTomorrowDraft = () => {
    if (selectedTaskIds.length === 0) return;
    const taskIds = [...selectedTaskIds].sort();
    const fingerprint = `${tomorrow}:${timezone}:${taskIds.join(",")}`;
    if (operationRef.current?.fingerprint !== fingerprint) {
      operationRef.current = { fingerprint, id: createOperationId() };
    }
    const operationId = operationRef.current.id;
    saveClosingState(storageKey, {
      selectedTaskIds: taskIds,
      fingerprint,
      operationId,
      planId: null,
    });
    createPlan.mutate({
      task_ids: taskIds,
      operation_id: operationId,
      range_start: toUtcISOString(`${tomorrow}T00:00`, timezone),
      range_end: toUtcISOString(`${afterTomorrow}T00:00`, timezone),
      strategy: "plan_tasks_only",
      ordering: "priority_deadline",
    }, {
      onSuccess: (plan) => {
        setCreatedPlan(plan);
        setKeptUnplaced(false);
        setTaskEditsSaved(false);
        saveClosingState(storageKey, {
          selectedTaskIds: taskIds,
          fingerprint,
          operationId,
          planId: plan.id,
        });
      },
    });
  };

  const removeUnplacedFromDraft = () => {
    if (!createdPlan) return;
    const items = Array.isArray(createdPlan.items) ? (createdPlan.items as PlanItem[]) : [];
    const unplacedIds = new Set(
      items
        .filter((item) => item.kind !== "plan_evidence" && item.state !== "placed" && item.task_id)
        .map((item) => item.task_id as string),
    );
    abandonPlan.mutate({
      planId: createdPlan.id,
      input: { expected_version: createdPlan.version ?? 1 },
    }, {
      onSuccess: () => {
        const nextSelection = selectedTaskIds.filter((id) => !unplacedIds.has(id));
        setSelectedTaskIds(nextSelection);
        setCreatedPlan(null);
        setDraftAbandoned(true);
        setKeptUnplaced(false);
        operationRef.current = null;
        saveClosingState(storageKey, {
          selectedTaskIds: nextSelection,
          fingerprint: null,
          operationId: null,
          planId: null,
        });
        setOpen(true);
      },
    });
  };

  const abandonDraftAndReselect = () => {
    if (!createdPlan) return;
    abandonPlan.mutate({
      planId: createdPlan.id,
      input: { expected_version: createdPlan.version ?? 1 },
    }, {
      onSuccess: () => {
        setSelectedTaskIds([]);
        setCreatedPlan(null);
        setDraftAbandoned(true);
        setKeptUnplaced(false);
        setTaskEditsSaved(false);
        operationRef.current = null;
        saveClosingState(storageKey, {
          selectedTaskIds: [],
          fingerprint: null,
          operationId: null,
          planId: null,
        });
        setOpen(true);
      },
    });
  };

  const adjustUnplacedTask = (task: Task) => {
    if (!createdPlan) return;
    abandonPlan.mutate({
      planId: createdPlan.id,
      input: { expected_version: createdPlan.version ?? 1 },
    }, {
      onSuccess: () => {
        setCreatedPlan(null);
        setDraftAbandoned(true);
        setKeptUnplaced(false);
        setTaskEditsSaved(false);
        operationRef.current = null;
        saveClosingState(storageKey, {
          selectedTaskIds,
          fingerprint: null,
          operationId: null,
          planId: null,
        });
        setEditingTask(task);
      },
    });
  };

  const outcome = createdPlan ? planOutcome(createdPlan) : null;

  return (
    <section aria-label="今天收尾与明日草案" className="mt-6 overflow-hidden rounded-2xl border border-amber-200/20 bg-gradient-to-br from-amber-200/[0.08] via-slate-900 to-emerald-300/[0.06]">
      <div className="flex flex-wrap items-start justify-between gap-4 p-5">
        <div>
            <p className="flex items-center gap-2 text-sm font-semibold text-amber-100">
              <Sprout size={18} aria-hidden="true" /> 今日收获
              <span className="rounded-full border border-emerald-200/20 bg-emerald-200/[0.08] px-2 py-0.5 text-xs text-emerald-100">
                已完成 {completedTasks.length} 项
              </span>
          </p>
          {completedTasks.length ? (
            <ul className="mt-3 flex flex-wrap gap-2">
              {completedTasks.slice(0, 4).map((task) => (
                <li key={task.id} className="inline-flex max-w-full items-center gap-2 rounded-full border border-emerald-200/20 bg-emerald-200/[0.08] px-3 py-1.5 text-sm text-emerald-100">
                  <Check size={14} aria-hidden="true" /> <span className="truncate">{task.title}</span>
                </li>
              ))}
              {completedTasks.length > 4 && (
                <li className="self-center text-xs text-slate-400">还有 {completedTasks.length - 4} 项</li>
              )}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-slate-400">今天完成的任务会收在这里。</p>
          )}
        </div>
        <button
          type="button"
          aria-expanded={open}
          aria-controls="day-closing-panel"
          onClick={() => setOpen((current) => !current)}
          className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-amber-100/20 bg-slate-950/40 px-4 text-sm font-medium text-amber-50 hover:bg-slate-950/70"
        >
          {open ? "收起今日收尾" : "整理明天"}
          <ChevronDown size={16} className={open ? "rotate-180 transition-transform" : "transition-transform"} />
        </button>
      </div>

      {open && (
        <div id="day-closing-panel" className="border-t border-white/10 p-5">
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.8fr)]">
            <div>
              <h3 className="text-base font-semibold text-white">还没完成的事</h3>
              <p className="mt-1 text-sm text-slate-400">勾选你希望带入明日草案的任务。未勾选的任务保持原样。</p>
              {unfinishedTasks.length ? (
                <fieldset className="mt-3 space-y-2">
                  <legend className="sr-only">选择带入明日草案的任务</legend>
                  {unfinishedTasks.map((task) => (
                    <label key={task.id} className="flex min-h-12 cursor-pointer items-center gap-3 rounded-xl border border-white/10 bg-slate-950/45 px-3 py-2 hover:border-amber-100/25">
                      <input
                        type="checkbox"
                        checked={selected.has(task.id)}
                        disabled={Boolean(createdPlan) || createPlan.isPending || abandonPlan.isPending}
                        onChange={() => toggleTask(task.id)}
                        className="size-4 accent-amber-300 disabled:cursor-not-allowed disabled:opacity-50"
                      />
                      <span className="min-w-0 flex-1 truncate text-sm text-slate-100">{task.title}</span>
                      {task.estimated_minutes && <span className="shrink-0 text-xs text-slate-500">约 {task.estimated_minutes} 分钟</span>}
                    </label>
                  ))}
                </fieldset>
              ) : (
                <p className="mt-3 rounded-xl bg-slate-950/45 p-3 text-sm text-slate-400">目前没有今日待收尾的任务。</p>
              )}
              {createPlan.isError && <p role="alert" className="mt-3 text-sm text-rose-200">明日草案暂时没有生成。任务状态和日程没有因此改变，请重试。</p>}
              {draftAbandoned && <p role="status" className="mt-3 text-sm text-emerald-200">草案已放弃；任务仍保留在任务列表中。</p>}
              <button
                type="button"
                disabled={selectedTaskIds.length === 0 || createPlan.isPending || Boolean(createdPlan)}
                onClick={createTomorrowDraft}
                className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-xl bg-amber-200 px-4 text-sm font-semibold text-slate-950 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {createPlan.isPending ? "正在整理草案…" : createdPlan ? "明日草案已生成" : `为 ${formatDateKey(tomorrow)} 生成草案`}
                <ArrowRight size={16} />
              </button>
            </div>

            <aside className="rounded-xl border border-white/10 bg-slate-950/45 p-4">
              <h3 className="text-sm font-semibold text-slate-100">明日安排先由你检查</h3>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                这里只创建任务计划草案。任务不会被标记为完成，正式日程也不会改变；你可以继续调整，再单独提交应用审批。
              </p>
              {createdPlan && outcome && (
                <div role="status" className="mt-4 rounded-xl border border-emerald-200/20 bg-emerald-200/[0.07] p-3">
                  <p className="text-sm font-medium text-emerald-100">明日草案已生成</p>
                  <p className="mt-1 text-xs text-slate-300">已安排 {outcome.placed} 项，未安排 {outcome.unplaced.length} 项。</p>
                  {outcome.unplaced.length > 0 && (
                    <>
                      <p className="mt-2 text-xs text-amber-100">有任务尚未找到合适时段；它们仍在草案中标记为未安排，没有被删除或延期。</p>
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-300">
                        {outcome.unplaced.map((item) => {
                          const task = unfinishedTasks.find((candidate) => candidate.id === item.task_id);
                          return <li key={item.task_id ?? item.reason_codes?.join(",")}>{task?.title ?? "未安排任务"}：没有找到符合当前日程和工作时段规则的空档。</li>;
                        })}
                      </ul>
                    </>
                  )}
                  {outcome.unplaced.length > 0 && (
                    <section aria-label="明日安排取舍" className="mt-3 rounded-xl border border-amber-200/20 bg-amber-200/[0.04] p-3">
                      <h4 className="text-sm font-medium text-amber-100">有任务放不进明天的安排</h4>
                      <p className="mt-1 text-xs leading-5 text-slate-400">你来决定下一步。系统不会自动缩短预计时长、减少缓冲或改截止时间。</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => setKeptUnplaced(true)}
                          disabled={keptUnplaced || abandonPlan.isPending}
                          className="inline-flex min-h-11 items-center rounded-lg border border-emerald-200/20 px-3 text-xs font-medium text-emerald-100 hover:bg-emerald-100/5 disabled:opacity-60"
                        >
                          {keptUnplaced ? "已保留未安排项" : "保留未安排项"}
                        </button>
                        <Link to={`/planning?plan_id=${encodeURIComponent(createdPlan.id)}`} className="inline-flex min-h-11 items-center gap-1 rounded-lg border border-cyan-200/20 px-3 text-xs font-medium text-cyan-100 hover:bg-cyan-100/5">
                          手动调整草案 <ArrowRight size={14} />
                        </Link>
                      </div>
                      {keptUnplaced && <p role="status" className="mt-2 text-xs text-emerald-200">未安排任务仍保留在这份草案中；正式任务和日程没有改变。</p>}
                      <div className="mt-3 border-t border-white/10 pt-3">
                        <p className="text-xs leading-5 text-slate-400">如果预计时长或缓冲需要调整，可以先编辑任务，再重新生成草案。当前草案会先放弃，任务本身仍保留。</p>
                        <ul className="mt-2 space-y-2">
                          {outcome.unplaced.map((item) => {
                            const task = unfinishedTasks.find((candidate) => candidate.id === item.task_id);
                            return task ? (
                              <li key={task.id} className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-300">
                                <span className="min-w-0 truncate">{task.title}</span>
                                <button
                                  type="button"
                                  disabled={abandonPlan.isPending}
                                  onClick={() => adjustUnplacedTask(task)}
                                  className="min-h-11 rounded-lg border border-white/10 px-3 font-medium text-slate-200 hover:bg-white/5 disabled:opacity-60"
                                >
                                  调整估时或缓冲
                                </button>
                              </li>
                            ) : null;
                          })}
                        </ul>
                        <p className="mt-2 text-xs leading-5 text-slate-400">也可以移除未安排项并重新选择。未勾选的任务仍保留在任务列表中。</p>
                      {abandonPlan.isError && <p role="alert" className="mt-2 text-xs text-rose-200">草案没有放弃，任务选择保持不变。请刷新后再试。</p>}
                      <button
                        type="button"
                        disabled={abandonPlan.isPending}
                        onClick={removeUnplacedFromDraft}
                        className="mt-2 inline-flex min-h-11 items-center rounded-lg border border-amber-100/20 px-3 text-xs font-medium text-amber-100 hover:bg-amber-100/5 disabled:opacity-60"
                      >
                        {abandonPlan.isPending ? "正在处理草案…" : "移除未安排项并重新选择"}
                      </button>
                      <button
                        type="button"
                        disabled={abandonPlan.isPending}
                        onClick={abandonDraftAndReselect}
                        className="ml-2 mt-2 inline-flex min-h-11 items-center rounded-lg border border-white/10 px-3 text-xs font-medium text-slate-200 hover:bg-white/5 disabled:opacity-60"
                      >
                        放弃草案并全部重选
                      </button>
                      </div>
                    </section>
                  )}
                  {outcome.unplaced.length === 0 && (
                    <>
                      <Link to={`/planning?plan_id=${encodeURIComponent(createdPlan.id)}`} className="mt-3 inline-flex min-h-11 items-center gap-2 text-sm font-medium text-cyan-200 hover:text-cyan-100">
                        检查草案 <ArrowRight size={15} />
                      </Link>
                      <button
                        type="button"
                        disabled={abandonPlan.isPending}
                        onClick={abandonDraftAndReselect}
                        className="ml-3 mt-3 inline-flex min-h-11 items-center rounded-lg border border-white/10 px-3 text-xs font-medium text-slate-200 hover:bg-white/5 disabled:opacity-60"
                      >
                        {abandonPlan.isPending ? "正在放弃草案…" : "放弃草案并重新选择"}
                      </button>
                    </>
                  )}
                </div>
              )}
              {taskEditsSaved && <p role="status" className="mt-3 text-xs leading-5 text-emerald-200">任务信息已更新。重新生成草案会使用新的预计时长和缓冲；这份草案尚未应用到正式日程。</p>}
            </aside>
          </div>
        </div>
      )}
      {editingTask && (
        <Suspense fallback={<p role="status" className="sr-only">正在打开任务编辑…</p>}>
          <TaskEditor
            key={editingTask.id}
            task={editingTask}
            timezone={timezone}
            onClose={() => setEditingTask(null)}
            onSaved={() => setTaskEditsSaved(true)}
          />
        </Suspense>
      )}
    </section>
  );
}
