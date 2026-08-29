import { Activity, CalendarCheck, GitCompare, Lock, Pause, Play, RefreshCw, RotateCcw, ShieldCheck, Trash2, Unlock, WandSparkles } from "lucide-react";
import { useMemo, useState } from "react";

import type { LocalReplanPreview, SchedulePlan } from "../api/planning";
import { useTasks } from "../features/tasks/hooks";
import { useCapacityForecast } from "../features/preferences/time-memory-hooks";
import {
  useApplyLocalReplan,
  useApplySchedulePlan,
  useAbandonSchedulePlan,
  useAutomationPolicies,
  useCompareSchedulePlans,
  useCreateSchedulePlan,
  useDetectScheduleDisruptions,
  useEditSchedulePlan,
  usePreviewLocalReplan,
  useRegenerateSchedulePlan,
  useRevertScheduleChangeBatch,
  useSaveAutomationPolicy,
  useUpdateAutomationPolicy,
  useValidateSchedulePlan,
} from "../features/planning/hooks";
import { ScheduleWorkspaceTabs } from "../features/workspace/schedule-workspace-tabs";

type PlanItem = {
  kind?: string;
  task_id?: string;
  state?: string;
  start_at?: string;
  end_at?: string;
  reason_codes?: string[];
  locked?: boolean;
  evidence?: Record<string, unknown>;
  segment_index?: number;
  segment_count?: number;
};

type ReplanItem = {
  task_id?: string;
  state?: string;
  from_start_at?: string;
  to_start_at?: string;
  to_end_at?: string;
  reason_codes?: string[];
};

function localInput(value: Date) {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function iso(value: string) {
  return new Date(value).toISOString();
}

function operationId() {
  return globalThis.crypto?.randomUUID?.() ?? `replan-${Date.now()}`;
}

const capacityRiskPresentation: Record<string, { label: string; className: string }> = {
  within_capacity: { label: "容量充足", className: "text-emerald-200" },
  tight: { label: "容量偏紧", className: "text-amber-200" },
  over_capacity: { label: "容量超载", className: "text-red-200" },
};

const capacityReasonLabels: Record<string, string> = {
  unplanned_exceeds_free_capacity: "未安排任务所需时间超过可用容量",
  commitments_and_unplanned_near_capacity: "已承诺与未安排工作接近可用容量",
  no_due_tasks_in_range: "所选范围内没有到期任务",
};

function itemsOf(plan: SchedulePlan | undefined): PlanItem[] {
  return Array.isArray(plan?.items) ? (plan.items as PlanItem[]) : [];
}

function movesOf(preview: LocalReplanPreview | undefined): ReplanItem[] {
  return Array.isArray(preview?.moved_items) ? (preview.moved_items as ReplanItem[]) : [];
}

export function PlanningPage() {
  const now = useMemo(() => new Date(), []);
  const tasks = useTasks();
  const createPlan = useCreateSchedulePlan();
  const applyPlan = useApplySchedulePlan();
  const comparePlans = useCompareSchedulePlans();
  const regeneratePlan = useRegenerateSchedulePlan();
  const editPlan = useEditSchedulePlan();
  const validatePlan = useValidateSchedulePlan();
  const abandonPlan = useAbandonSchedulePlan();
  const policies = useAutomationPolicies();
  const savePolicy = useSaveAutomationPolicy();
  const updatePolicy = useUpdateAutomationPolicy();
  const detectDisruptions = useDetectScheduleDisruptions();
  const previewReplan = usePreviewLocalReplan();
  const applyReplan = useApplyLocalReplan();
  const revertBatch = useRevertScheduleChangeBatch();
  const [mode, setMode] = useState<"plan" | "replan">("plan");
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<SchedulePlan>();
  const [regenerateTaskIds, setRegenerateTaskIds] = useState<string[]>([]);
  const [ordering, setOrdering] = useState<"priority_deadline" | "longest_first">("priority_deadline");
  const [strategy, setStrategy] = useState<"plan_tasks_only" | "create_linked_event_blocks">("plan_tasks_only");
  const [rangeStart, setRangeStart] = useState(localInput(now));
  const [rangeEnd, setRangeEnd] = useState(localInput(new Date(now.getTime() + 7 * 86_400_000)));
  const [blockedStart, setBlockedStart] = useState(localInput(now));
  const [blockedEnd, setBlockedEnd] = useState(localInput(new Date(now.getTime() + 60 * 60_000)));
  const [horizonEnd, setHorizonEnd] = useState(localInput(new Date(now.getTime() + 2 * 86_400_000)));
  const [movableTaskIds, setMovableTaskIds] = useState<string[]>([]);
  const [selectedPolicyId, setSelectedPolicyId] = useState("");
  const capacityRange = useMemo(() => {
    if (!rangeStart || !rangeEnd) return undefined;
    const start = new Date(rangeStart);
    const end = new Date(rangeEnd);
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
      return undefined;
    }
    return { range_start: start.toISOString(), range_end: end.toISOString() };
  }, [rangeEnd, rangeStart]);
  const capacity = useCapacityForecast(capacityRange);

  const activeTasks = (tasks.data ?? []).filter(
    (task) => task.status === "pending" || task.status === "in_progress",
  );
  const plannedTasks = activeTasks.filter((task) => task.planned_start_at && task.planned_end_at);
  const taskTitles = new Map(activeTasks.map((task) => [task.id, task.title]));
  const selectedPolicy = policies.data?.find((policy) => policy.id === selectedPolicyId);
  const planItems = itemsOf(selectedPlan);
  const replanItems = movesOf(previewReplan.data);

  const detectCurrentDisruptions = () => {
    detectDisruptions.mutate(
      { range_start: iso(blockedStart), range_end: iso(horizonEnd) },
      {
        onSuccess: (items) => {
          if (!items.length) return;
          const firstStart = items.reduce(
            (current, item) => item.blocked_start < current ? item.blocked_start : current,
            items[0].blocked_start,
          );
          const lastEnd = items.reduce(
            (current, item) => item.blocked_end > current ? item.blocked_end : current,
            items[0].blocked_end,
          );
          setBlockedStart(localInput(new Date(firstStart)));
          setBlockedEnd(localInput(new Date(lastEnd)));
          setMovableTaskIds([...new Set(items.map((item) => item.task_id))]);
        },
      },
    );
  };

  const toggle = (values: string[], id: string, setter: (next: string[]) => void) => {
    setter(values.includes(id) ? values.filter((value) => value !== id) : [...values, id]);
  };

  const setPlanningPreset = (preset: "day" | "week") => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + (preset === "day" ? 1 : 7));
    setRangeStart(localInput(start));
    setRangeEnd(localInput(end));
  };

  const generatePlan = () => {
    createPlan.mutate({
      task_ids: selectedTaskIds,
      range_start: iso(rangeStart),
      range_end: iso(rangeEnd),
      strategy,
      ordering,
    }, { onSuccess: (plan) => { setSelectedPlan(plan); setRegenerateTaskIds([]); } });
  };

  const comparePlanOptions = () => {
    comparePlans.mutate({
      task_ids: selectedTaskIds,
      range_start: iso(rangeStart),
      range_end: iso(rangeEnd),
      strategy,
    }, { onSuccess: (result) => { setSelectedPlan(result.alternatives[0]); setRegenerateTaskIds([]); } });
  };

  const regenerateSelected = () => {
    if (!selectedPlan) return;
    regeneratePlan.mutate({
      planId: selectedPlan.id,
      input: {
        expected_version: selectedPlan.version ?? 1,
        task_ids: regenerateTaskIds,
        ordering,
      },
    }, { onSuccess: (plan) => { setSelectedPlan(plan); setRegenerateTaskIds([]); } });
  };

  const generateReplan = () => {
    previewReplan.mutate({
      blocked_start: iso(blockedStart),
      blocked_end: iso(blockedEnd),
      movable_task_ids: movableTaskIds,
      horizon_end: iso(horizonEnd),
    });
  };

  const applyGeneratedPlan = () => {
    const plan = selectedPlan;
    if (!plan) return;
    applyPlan.mutate({
      planId: plan.id,
      input: { expected_version: plan.version ?? 1 },
    }, { onSuccess: setSelectedPlan });
  };

  const setItemLocked = (item: PlanItem, locked: boolean) => {
    if (!selectedPlan || !item.task_id) return;
    editPlan.mutate({
      planId: selectedPlan.id,
      input: {
        expected_version: selectedPlan.version ?? 1,
        items: [{ task_id: item.task_id, locked }],
      },
    }, { onSuccess: setSelectedPlan });
  };

  const validateSelectedPlan = () => {
    if (!selectedPlan) return;
    validatePlan.mutate({
      planId: selectedPlan.id,
      input: { expected_version: selectedPlan.version ?? 1 },
    }, { onSuccess: (result) => setSelectedPlan(result.plan) });
  };

  const abandonSelectedPlan = () => {
    if (!selectedPlan) return;
    abandonPlan.mutate({
      planId: selectedPlan.id,
      input: { expected_version: selectedPlan.version ?? 1 },
    }, { onSuccess: setSelectedPlan });
  };

  return (
    <section className="mx-auto max-w-6xl space-y-6">
      <ScheduleWorkspaceTabs />
      <header className="flex flex-wrap items-end justify-between gap-4 pt-2 lg:pt-6">
        <div>
          <h2 className="text-3xl font-semibold">规划工作台</h2>
          <p className="mt-2 text-sm text-slate-400">先预览约束结果，再确认写入日程事实。</p>
        </div>
        <div className="inline-flex rounded-lg border border-white/10 bg-slate-900 p-1" role="tablist">
          <ModeButton active={mode === "plan"} onClick={() => setMode("plan")}>计划草案</ModeButton>
          <ModeButton active={mode === "replan"} onClick={() => setMode("replan")}>局部调整</ModeButton>
        </div>
      </header>

      <section className="border-y border-white/10 py-4" aria-labelledby="capacity-heading">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-cyan-300" />
            <h3 id="capacity-heading" className="font-semibold">所选范围容量</h3>
          </div>
          {capacity.data && (
            <span className={`text-sm font-semibold ${capacityRiskPresentation[capacity.data.risk]?.className ?? "text-slate-300"}`}>
              {capacityRiskPresentation[capacity.data.risk]?.label ?? capacity.data.risk}
            </span>
          )}
        </div>
        {capacity.isPending && <p className="mt-3 text-sm text-slate-500">正在计算容量…</p>}
        {capacity.isError && <p role="alert" className="mt-3 text-sm text-amber-200">容量预测暂时不可用，仍可手动生成计划。</p>}
        {capacity.data && (
          <div className="mt-3">
            <dl className="grid grid-cols-3 gap-3 text-sm">
              <CapacityValue label="可用时间" minutes={capacity.data.available_minutes} />
              <CapacityValue label="已计划任务" minutes={capacity.data.committed_minutes} />
              <CapacityValue label="未安排任务" minutes={capacity.data.unplanned_minutes} />
            </dl>
            {capacity.data.reason_codes.length > 0 && (
              <p className="mt-3 text-xs text-slate-400">
                {capacity.data.reason_codes.map((code) => capacityReasonLabels[code] ?? code).join("；")}
              </p>
            )}
          </div>
        )}
      </section>

      {mode === "plan" ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <section className="rounded-lg border border-white/10 bg-slate-900 p-5">
            <h3 className="flex items-center gap-2 font-semibold"><WandSparkles size={19} />选择待安排任务</h3>
            <div className="mt-4 max-h-80 space-y-2 overflow-auto">
              {activeTasks.map((task) => (
                <label key={task.id} className="flex min-h-12 cursor-pointer items-center gap-3 border-b border-white/10 py-2 text-sm">
                  <input type="checkbox" checked={selectedTaskIds.includes(task.id)} onChange={() => toggle(selectedTaskIds, task.id, setSelectedTaskIds)} />
                  <span className="min-w-0 flex-1 truncate">{task.title}</span>
                  <span className="text-xs text-slate-500">{task.estimated_minutes ?? 30} 分钟</span>
                </label>
              ))}
              {!activeTasks.length && <p className="text-sm text-slate-500">暂无可安排任务。</p>}
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <DateField label="开始" value={rangeStart} onChange={setRangeStart} />
              <DateField label="结束" value={rangeEnd} onChange={setRangeEnd} />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2" aria-label="规划范围快捷选择">
              <button type="button" onClick={() => setPlanningPreset("day")} className="min-h-10 rounded-lg border border-white/10 text-sm text-slate-200">Plan My Day</button>
              <button type="button" onClick={() => setPlanningPreset("week")} className="min-h-10 rounded-lg border border-white/10 text-sm text-slate-200">Plan My Week</button>
            </div>
            <label className="mt-4 block text-xs text-slate-400">排序策略
              <select value={ordering} onChange={(event) => setOrdering(event.target.value as typeof ordering)} className="mt-1 min-h-11 w-full rounded-lg border border-white/10 bg-slate-950 px-3 text-sm text-slate-100">
                <option value="priority_deadline">优先级与截止时间</option>
                <option value="longest_first">长任务优先</option>
              </select>
            </label>
            <label className="mt-4 block text-xs text-slate-400">应用方式
              <select value={strategy} onChange={(event) => setStrategy(event.target.value as typeof strategy)} className="mt-1 min-h-11 w-full rounded-lg border border-white/10 bg-slate-950 px-3 text-sm text-slate-100">
                <option value="plan_tasks_only">写入任务计划区间</option>
                <option value="create_linked_event_blocks">创建关联日历块（支持拆分）</option>
              </select>
            </label>
            <button type="button" disabled={!selectedTaskIds.length || createPlan.isPending} onClick={generatePlan} className="mt-4 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-cyan-300 px-4 font-semibold text-slate-950 disabled:opacity-40">
              <CalendarCheck size={18} />{createPlan.isPending ? "生成中…" : "生成草案"}
            </button>
            <button type="button" disabled={!selectedTaskIds.length || comparePlans.isPending} onClick={comparePlanOptions} className="mt-2 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg border border-cyan-300/30 px-4 text-sm font-semibold text-cyan-200 disabled:opacity-40">
              <GitCompare size={18} />{comparePlans.isPending ? "比较中…" : "比较两种方案"}
            </button>
            {createPlan.isError && <ErrorText error={createPlan.error} />}
            {comparePlans.isError && <ErrorText error={comparePlans.error} />}
          </section>

          <section className="rounded-lg border border-white/10 bg-slate-900 p-5">
            <h3 className="font-semibold">草案结果</h3>
            {!selectedPlan && <p className="mt-4 text-sm text-slate-500">尚未生成草案。</p>}
            {selectedPlan && (
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-400">
                <span>状态 {selectedPlan.status}</span>
                <span>v{selectedPlan.version}</span>
                {selectedPlan.expires_at && (
                  <span>有效至 {new Date(selectedPlan.expires_at).toLocaleString()}</span>
                )}
                {selectedPlan.invalidation_reason && <span className="text-red-200">失效原因 {selectedPlan.invalidation_reason}</span>}
              </div>
            )}
            {comparePlans.data && (
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {comparePlans.data.alternatives.map((plan, index) => {
                  const metric = comparePlans.data.comparison[index] as Record<string, unknown>;
                  return <button key={plan.id} type="button" onClick={() => { setSelectedPlan(plan); setRegenerateTaskIds([]); }} className={`min-h-14 rounded-lg border px-3 text-left text-xs ${selectedPlan?.id === plan.id ? "border-cyan-300 text-cyan-100" : "border-white/10 text-slate-400"}`}>
                    <span className="block font-medium">{metric.ordering === "longest_first" ? "长任务优先" : "优先级与截止时间"}</span>
                    <span>{String(metric.placed_count)} 已安排 · {String(metric.unplaced_count)} 未安排</span>
                  </button>;
                })}
              </div>
            )}
            <div className="mt-4 space-y-3">
              {planItems.filter((item) => item.kind !== "plan_evidence").map((item, index) => (
                <div key={`${item.task_id}-${item.segment_index ?? index}`} className="border-b border-white/10 pb-3 text-sm">
                  <div className="flex justify-between gap-4"><label className="flex min-w-0 items-center gap-2"><input type="checkbox" disabled={item.locked} checked={regenerateTaskIds.includes(item.task_id ?? "")} onChange={() => item.task_id && toggle(regenerateTaskIds, item.task_id, setRegenerateTaskIds)} /><span className="truncate">{taskTitles.get(item.task_id ?? "") ?? item.task_id}{(item.segment_count ?? 1) > 1 ? ` · 片段 ${item.segment_index}/${item.segment_count}` : ""}</span></label><div className="flex shrink-0 items-center gap-2"><span className={item.state === "placed" ? "text-emerald-300" : "text-amber-300"}>{item.state === "placed" ? "已安排" : "未安排"}</span>{item.state === "placed" && selectedPlan?.status === "draft" && (item.segment_count ?? 1) === 1 && <button type="button" title={item.locked ? "解锁计划块" : "锁定计划块"} aria-label={item.locked ? `解锁计划块：${taskTitles.get(item.task_id ?? "") ?? item.task_id}` : `锁定计划块：${taskTitles.get(item.task_id ?? "") ?? item.task_id}`} disabled={editPlan.isPending} onClick={() => setItemLocked(item, !item.locked)} className="rounded-md p-2 text-slate-300 hover:bg-white/10 disabled:opacity-40">{item.locked ? <Unlock size={16} /> : <Lock size={16} />}</button>}</div></div>
                  {item.start_at && <p className="mt-1 text-xs text-slate-400">{new Date(item.start_at).toLocaleString()} - {new Date(item.end_at ?? item.start_at).toLocaleTimeString()}</p>}
                  {item.reason_codes?.length ? <p className="mt-1 text-xs text-amber-200">{item.reason_codes.join(" · ")}</p> : null}
                </div>
              ))}
            </div>
            {selectedPlan?.status === "draft" && regenerateTaskIds.length > 0 && (
              <button type="button" disabled={regeneratePlan.isPending} onClick={regenerateSelected} className="mt-4 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg border border-cyan-300/30 px-4 text-sm font-semibold text-cyan-200 disabled:opacity-40"><RefreshCw size={17} />{regeneratePlan.isPending ? "重生成中…" : "只重生成选中项"}</button>
            )}
            {regeneratePlan.isError && <ErrorText error={regeneratePlan.error} />}
            {editPlan.isError && <ErrorText error={editPlan.error} />}
            {selectedPlan?.status === "draft" && (
              <div className="mt-5 grid gap-2 sm:grid-cols-3">
                <button type="button" disabled={validatePlan.isPending} onClick={validateSelectedPlan} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-cyan-300/30 px-3 text-sm text-cyan-200 disabled:opacity-40"><ShieldCheck size={16} />验证</button>
                <button type="button" disabled={abandonPlan.isPending} onClick={abandonSelectedPlan} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-red-300/30 px-3 text-sm text-red-200 disabled:opacity-40"><Trash2 size={16} />放弃</button>
                <button type="button" disabled={applyPlan.isPending} onClick={applyGeneratedPlan} className="min-h-11 rounded-lg border border-emerald-300/40 px-4 font-semibold text-emerald-200 disabled:opacity-40">{applyPlan.isPending ? "应用中…" : "确认应用"}</button>
              </div>
            )}
            {validatePlan.data && <p role="status" className={`mt-3 text-sm ${validatePlan.data.valid ? "text-emerald-200" : "text-red-200"}`}>{validatePlan.data.valid ? "草案仍然有效。" : `草案已失效：${validatePlan.data.reason_codes.join("、")}`}</p>}
            {validatePlan.isError && <ErrorText error={validatePlan.error} />}
            {abandonPlan.isError && <ErrorText error={abandonPlan.error} />}
            {applyPlan.isSuccess && <p role="status" className="mt-3 text-sm text-emerald-200">计划已应用。</p>}
            {applyPlan.isError && <ErrorText error={applyPlan.error} />}
          </section>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <section className="rounded-lg border border-white/10 bg-slate-900 p-5">
            <div className="flex items-center justify-between gap-3"><h3 className="flex items-center gap-2 font-semibold"><ShieldCheck size={19} />授权策略</h3><span className="text-xs text-slate-500">后端强制执行</span></div>
            <select value={selectedPolicyId} onChange={(event) => setSelectedPolicyId(event.target.value)} className="mt-4 min-h-11 w-full rounded-lg border border-white/10 bg-slate-950 px-3">
              <option value="">选择策略</option>
              {policies.data?.map((policy) => <option key={policy.id} value={policy.id}>{policy.name}{policy.requires_approval ? "（需审批）" : ""}</option>)}
            </select>
            {selectedPolicy && (
              <div className="mt-3 grid gap-2">
                <button
                  type="button"
                  disabled={updatePolicy.isPending}
                  onClick={() => updatePolicy.mutate({ policyId: selectedPolicy.id, input: { enabled: !selectedPolicy.enabled } })}
                  className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-lg border border-white/10 text-sm text-slate-200 disabled:opacity-40"
                >
                  {selectedPolicy.enabled ? <Pause size={16} /> : <Play size={16} />}
                  {selectedPolicy.enabled ? "暂停这条自动化策略" : "恢复这条自动化策略"}
                </button>
                <button
                  type="button"
                  disabled={updatePolicy.isPending || !movableTaskIds.length}
                  onClick={() => updatePolicy.mutate({ policyId: selectedPolicy.id, input: { authorized_task_ids: movableTaskIds } })}
                  className="min-h-10 rounded-lg border border-cyan-300/25 text-sm text-cyan-100 disabled:opacity-40"
                >
                  授权当前选中的 {movableTaskIds.length} 个任务
                </button>
                <p className="text-xs text-slate-500">已持久授权 {selectedPolicy.authorized_task_ids?.length ?? 0} 个任务</p>
              </div>
            )}
            {!policies.data?.length && (
              <button type="button" disabled={savePolicy.isPending || !movableTaskIds.length} onClick={() => savePolicy.mutate({ name: "柔性任务局部调整", enabled: true, allow_task_reschedule: true, max_moves_per_run: 3, requires_approval: false, authorized_task_ids: movableTaskIds })} className="mt-3 min-h-11 w-full rounded-lg border border-cyan-300/30 text-sm text-cyan-200 disabled:opacity-40">
                为已选任务创建免审批策略
              </button>
            )}
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <DateField label="阻塞开始" value={blockedStart} onChange={setBlockedStart} />
              <DateField label="阻塞结束" value={blockedEnd} onChange={setBlockedEnd} />
            </div>
            <div className="mt-3"><DateField label="调整范围截止" value={horizonEnd} onChange={setHorizonEnd} /></div>
            <button
              type="button"
              disabled={detectDisruptions.isPending}
              onClick={detectCurrentDisruptions}
              className="mt-4 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg border border-amber-300/30 text-sm font-medium text-amber-100 disabled:opacity-40"
            >
              <Activity size={17} />{detectDisruptions.isPending ? "检测中…" : "检测日程扰动"}
            </button>
            {detectDisruptions.data?.length === 0 && <p role="status" className="mt-2 text-xs text-emerald-200">当前范围没有发现任务与日程重叠。</p>}
            {detectDisruptions.isError && <ErrorText error={detectDisruptions.error} />}
            <div className="mt-4 max-h-64 space-y-2 overflow-auto">
              {plannedTasks.map((task) => (
                <label key={task.id} className="flex min-h-12 cursor-pointer items-center gap-3 border-b border-white/10 py-2 text-sm">
                  <input type="checkbox" checked={movableTaskIds.includes(task.id)} onChange={() => toggle(movableTaskIds, task.id, setMovableTaskIds)} />
                  <span className="min-w-0 flex-1 truncate">{task.title}</span>
                  <span className="text-xs text-slate-500">{new Date(task.planned_start_at as string).toLocaleString()}</span>
                </label>
              ))}
            </div>
            <button type="button" disabled={!movableTaskIds.length || previewReplan.isPending} onClick={generateReplan} className="mt-5 min-h-11 w-full rounded-lg bg-cyan-300 px-4 font-semibold text-slate-950 disabled:opacity-40">{previewReplan.isPending ? "计算中…" : "预览局部调整"}</button>
            {previewReplan.isError && <ErrorText error={previewReplan.error} />}
          </section>

          <section className="rounded-lg border border-white/10 bg-slate-900 p-5">
            <h3 className="font-semibold">变化预览</h3>
            {detectDisruptions.data && detectDisruptions.data.length > 0 && (
              <div className="mt-4 border-l-2 border-amber-300/40 pl-4">
                <p className="text-xs font-medium text-amber-100">影响时间线</p>
                <div className="mt-3 space-y-3">
                  {detectDisruptions.data.map((item) => (
                    <div key={`${item.task_id}-${item.event_id}`} className="text-sm">
                      <p className="text-slate-200">{item.event_title} 与 {item.task_title} 重叠</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {new Date(item.blocked_start).toLocaleString()} · {item.overlap_minutes} 分钟
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {!previewReplan.data && <p className="mt-4 text-sm text-slate-500">尚未生成变化。</p>}
            {previewReplan.data && <p className="mt-3 text-xs text-slate-400">移动 {previewReplan.data.stability_cost.moved_count ?? 0} 项 · 总位移 {previewReplan.data.stability_cost.total_move_minutes ?? 0} 分钟 · 未放置 {previewReplan.data.stability_cost.unplaced_count ?? 0} 项</p>}
            <div className="mt-4 space-y-3">
              {replanItems.map((item) => (
                <div key={item.task_id} className="border-b border-white/10 pb-3 text-sm">
                  <div className="flex justify-between gap-4"><span>{taskTitles.get(item.task_id ?? "") ?? item.task_id}</span><span className={item.state === "moved" ? "text-emerald-300" : "text-amber-300"}>{item.state === "moved" ? "可移动" : "保持原位"}</span></div>
                  {item.to_start_at && <p className="mt-1 text-xs text-slate-400">调整至 {new Date(item.to_start_at).toLocaleString()}</p>}
                  {item.reason_codes?.length ? <p className="mt-1 text-xs text-slate-500">{item.reason_codes.join(" · ")}</p> : null}
                </div>
              ))}
            </div>
            {previewReplan.data && selectedPolicy && !selectedPolicy.requires_approval && (
              <button type="button" disabled={applyReplan.isPending} onClick={() => applyReplan.mutate({ blocked_start: iso(blockedStart), blocked_end: iso(blockedEnd), movable_task_ids: movableTaskIds, horizon_end: iso(horizonEnd), policy_id: selectedPolicy.id, operation_id: operationId() })} className="mt-5 min-h-11 w-full rounded-lg border border-emerald-300/40 font-semibold text-emerald-200 disabled:opacity-40">{applyReplan.isPending ? "执行中…" : "执行这次调整"}</button>
            )}
            {selectedPolicy?.requires_approval && <p className="mt-4 text-sm text-amber-200">此策略要求 HITL 审批，当前页面不会直接执行。</p>}
            {applyReplan.isError && <ErrorText error={applyReplan.error} />}
            {applyReplan.data && (
              <div className="mt-4 flex items-center justify-between gap-3 rounded-lg bg-emerald-300/10 p-3 text-sm text-emerald-100"><span>变更批次已应用</span><button type="button" disabled={revertBatch.isPending} onClick={() => revertBatch.mutate(applyReplan.data.id)} className="inline-flex items-center gap-2 rounded-lg border border-emerald-200/30 px-3 py-2"><RotateCcw size={16} />撤销</button></div>
            )}
            {revertBatch.isSuccess && <p role="status" className="mt-3 text-sm text-emerald-200">已恢复调整前安排。</p>}
            {revertBatch.isError && <ErrorText error={revertBatch.error} />}
          </section>
        </div>
      )}
    </section>
  );
}

function ModeButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: string }) {
  return <button type="button" role="tab" aria-selected={active} onClick={onClick} className={`min-h-10 rounded-md px-4 text-sm font-medium ${active ? "bg-cyan-300 text-slate-950" : "text-slate-300"}`}>{children}</button>;
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="block text-xs text-slate-400"><span>{label}</span><input type="datetime-local" value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 min-h-11 w-full rounded-lg border border-white/10 bg-slate-950 px-3 text-sm text-slate-100" /></label>;
}

function ErrorText({ error }: { error: Error }) {
  return <p role="alert" className="mt-3 text-sm text-red-200">{error.message}</p>;
}

function CapacityValue({ label, minutes }: { label: string; minutes: number }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-1 font-semibold text-slate-100">{minutes} 分钟</dd>
    </div>
  );
}
