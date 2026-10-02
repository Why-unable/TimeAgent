import type { SchedulePlan } from "../../api/planning";
import { formatInUserTimezone, formatTimeInUserTimezone } from "../../utils/datetime";

type PlanItem = {
  kind?: string;
  task_id?: string;
  state?: string;
  start_at?: string;
  end_at?: string;
  planning_order?: number;
  locked?: boolean;
  segment_index?: number;
  reason_codes?: string[];
};

function items(plan: SchedulePlan) {
  return (Array.isArray(plan.items) ? plan.items : []) as PlanItem[];
}

function key(item: PlanItem) {
  return `${item.task_id ?? "unknown"}:${item.segment_index ?? 1}`;
}

function dateRange(item: PlanItem, timezone: string) {
  if (!item.start_at) return "尚未安排";
  return `${formatInUserTimezone(item.start_at, timezone)} ${formatTimeInUserTimezone(item.start_at, timezone)}–${formatTimeInUserTimezone(item.end_at ?? item.start_at, timezone)}`;
}

export function PlanDiffReview({
  previous,
  current,
  timezone,
  taskTitles,
}: {
  previous: SchedulePlan;
  current: SchedulePlan;
  timezone: string;
  taskTitles: Map<string, string>;
}) {
  const before = new Map(items(previous).filter((item) => item.kind !== "plan_evidence").map((item) => [key(item), item]));
  const after = new Map(items(current).filter((item) => item.kind !== "plan_evidence").map((item) => [key(item), item]));
  const allKeys = new Set([...before.keys(), ...after.keys()]);
  const changes = [...allKeys].flatMap((itemKey) => {
    const oldItem = before.get(itemKey);
    const newItem = after.get(itemKey);
    const item = newItem ?? oldItem;
    if (!item) return [];
    const timeChanged = oldItem?.start_at !== newItem?.start_at || oldItem?.end_at !== newItem?.end_at;
    const stateChanged = oldItem?.state !== newItem?.state;
    const orderChanged = oldItem?.planning_order !== newItem?.planning_order;
    const lockChanged = oldItem?.locked !== newItem?.locked;
    if (oldItem && newItem && !timeChanged && !stateChanged && !orderChanged && !lockChanged) return [];
    const title = taskTitles.get(item.task_id ?? "") ?? "任务";
    const detail = !oldItem
      ? `加入计划 · ${dateRange(newItem!, timezone)}`
      : !newItem
        ? "已从这份草案移除"
        : [
          timeChanged ? `${dateRange(oldItem, timezone)} → ${dateRange(newItem, timezone)}` : null,
          stateChanged && newItem.state !== "placed" ? "暂时未安排" : null,
          orderChanged ? "任务顺序已调整" : null,
          lockChanged ? (newItem.locked ? "已固定时间" : "已解除固定") : null,
          newItem.reason_codes?.length ? newItem.reason_codes.map((code) => ({
            deadline_before_range: "截止时间早于计划范围",
            planning_decision_window_empty: "指定条件下没有可安排时间",
            planning_predecessor_unavailable: "前置任务尚未安排",
            exact_start_outside_allowed_window: "指定时间超出可安排时段",
            exact_start_unavailable: "指定时间与现有安排冲突",
            insufficient_free_capacity: "可用时间不足",
            task_planning_locked: "任务当前已锁定",
          }[code] ?? code.replaceAll("_", " "))).join(" · ") : null,
        ].filter(Boolean).join(" · ");
    return [{ key: itemKey, title, detail }];
  });
  if (!changes.length) return null;
  const unchangedCount = Math.max(0, after.size - changes.filter((change) => after.has(change.key)).length);

  return (
    <details open className="mb-3 rounded-xl border border-cyan-200/25 bg-cyan-200/5 p-3">
      <summary className="min-h-11 cursor-pointer text-sm font-semibold text-cyan-100">本次调整 · {changes.length} 项</summary>
      <ul className="mt-2 space-y-2">
        {changes.map((change) => <li key={change.key} className="rounded-lg bg-slate-950/40 p-2 text-sm">
          <p className="font-medium text-slate-100">{change.title}</p>
          <p className="mt-1 text-xs text-slate-300">{change.detail}</p>
        </li>)}
      </ul>
      {unchangedCount > 0 && <p className="mt-2 text-xs text-slate-400">其余 {unchangedCount} 项安排保持不变。</p>}
    </details>
  );
}
