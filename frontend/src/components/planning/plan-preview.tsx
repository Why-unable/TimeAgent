import { Lock } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { SchedulePlan } from "../../api/planning";
import { formatInUserTimezone, formatTimeInUserTimezone } from "../../utils/datetime";
import { InteractivePlanningSurface } from "./interactive-planning-surface";
import { PlanDiffReview } from "./plan-diff-review";

export interface PlanPreviewItem {
  task_id?: string;
  state?: string;
  start_at?: string;
  end_at?: string;
  locked?: boolean;
  reason_codes?: string[];
  segment_index?: number;
  segment_count?: number;
}

export function PlanPreview({
  items,
  taskTitles,
  timezone,
  plan,
  onPlanChange,
  onRefreshPlan,
  conversationId,
  agentRunId,
  agentRunActive,
}: {
  items: PlanPreviewItem[];
  taskTitles: Map<string, string>;
  timezone: string;
  plan?: SchedulePlan;
  onPlanChange?: (plan: SchedulePlan) => void;
  onRefreshPlan?: () => Promise<void>;
  conversationId?: string;
  agentRunId?: string;
  agentRunActive?: boolean;
}) {
  const previousPlan = useRef(plan);
  const [diffFrom, setDiffFrom] = useState<SchedulePlan>();
  const placed = items.filter((item) => item.state === "placed" && item.start_at).slice().sort(
    (left, right) => new Date(left.start_at as string).getTime() - new Date(right.start_at as string).getTime(),
  );
  const unplaced = items.filter((item) => item.state !== "placed");

  const unplacedReasonLabel = (code: string) => ({
    deadline_before_range: "截止时间早于这份计划的范围",
    planning_decision_window_empty: "指定条件下没有可安排的时间",
    planning_predecessor_unavailable: "前置任务尚未安排",
    exact_start_outside_allowed_window: "指定时间超出可安排时段",
    exact_start_unavailable: "指定时间与现有安排冲突",
    insufficient_free_capacity: "当前可用时间不足",
    task_planning_locked: "任务当前已锁定",
  }[code] ?? code.replaceAll("_", " "));

  useEffect(() => {
    const previous = previousPlan.current;
    if (
      plan
      && previous
      && plan.id === previous.id
      && plan.version !== undefined
      && previous.version !== undefined
      && plan.version > previous.version
      && plan.status === "draft"
    ) {
      setDiffFrom(previous);
    } else if (plan?.id !== previous?.id) {
      setDiffFrom(undefined);
    }
    previousPlan.current = plan;
  }, [plan]);

  if (items.length === 0) return null;

  return (
    <section aria-label="计划时间线" className="mt-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-200">安排预览</h4>
        {plan && <span className={`rounded-full px-3 py-1 text-xs font-medium ${plan.status === "draft" ? "border border-cyan-200/30 bg-cyan-200/10 text-cyan-100" : plan.status === "applied" ? "border border-emerald-200/30 bg-emerald-200/10 text-emerald-100" : "border border-amber-200/30 bg-amber-200/10 text-amber-100"}`}>
          {plan.status === "draft" ? "计划草稿 · 尚未应用到日程" : plan.status === "applied" ? "已应用到日程" : "计划需要重新检查"}
        </span>}
      </div>
      {diffFrom && plan && <PlanDiffReview previous={diffFrom} current={plan} timezone={timezone} taskTitles={taskTitles} />}
      {plan?.status === "draft" && (
        <InteractivePlanningSurface
          plan={plan}
          taskTitles={taskTitles}
          timezone={timezone}
          onPlanChange={onPlanChange}
          onRefreshPlan={onRefreshPlan}
          conversationId={conversationId}
          agentRunId={agentRunId}
          agentRunActive={agentRunActive}
        />
      )}
      {plan?.status !== "draft" && <>
      {placed.length > 0 && <ol className="ml-2 space-y-0 border-l border-cyan-300/25">
        {placed.map((item, index) => {
          const title = taskTitles.get(item.task_id ?? "") ?? "任务";
          return <li key={`${item.task_id}-${item.segment_index ?? index}`} className="relative pb-4 pl-5 last:pb-1">
            <span aria-hidden="true" className="absolute -left-[5px] top-1.5 size-2.5 rounded-full border-2 border-cyan-300 bg-slate-900" />
            <p className="text-xs font-medium text-cyan-200">{formatInUserTimezone(item.start_at as string, timezone)} – {formatTimeInUserTimezone(item.end_at ?? item.start_at as string, timezone)}</p>
            <div className="mt-1 flex items-center gap-2 text-sm text-slate-100">
              <span className="min-w-0 flex-1">{title}{(item.segment_count ?? 1) > 1 ? ` · 片段 ${item.segment_index}/${item.segment_count}` : ""}</span>
              {item.locked && <span className="inline-flex items-center gap-1 text-xs text-slate-400"><Lock size={12} />已固定</span>}
            </div>
          </li>;
        })}
      </ol>}
      </>}
      {unplaced.length > 0 && <div className="mt-4 border-t border-white/10 pt-3">
        <p className="text-xs font-semibold text-amber-200">未安排 · {unplaced.length} 项</p>
        <ul className="mt-2 space-y-2">{unplaced.map((item, index) => <li key={`${item.task_id}-${index}`} className="text-sm text-slate-200"><span>{taskTitles.get(item.task_id ?? "") ?? "任务"}</span><p className="mt-1 text-xs text-slate-400">{item.reason_codes?.length ? item.reason_codes.map(unplacedReasonLabel).join(" · ") : "暂时没有合适的安排位置；你可以调整计划范围或任务。"}</p></li>)}</ul>
      </div>}
    </section>
  );
}
