import { Lock } from "lucide-react";

import { formatInUserTimezone, formatTimeInUserTimezone } from "../../utils/datetime";

export interface PlanPreviewItem {
  task_id?: string;
  state?: string;
  start_at?: string;
  end_at?: string;
  locked?: boolean;
  segment_index?: number;
  segment_count?: number;
}

export function PlanPreview({
  items,
  taskTitles,
  timezone,
}: {
  items: PlanPreviewItem[];
  taskTitles: Map<string, string>;
  timezone: string;
}) {
  const placed = items.filter((item) => item.state === "placed" && item.start_at).slice().sort(
    (left, right) => new Date(left.start_at as string).getTime() - new Date(right.start_at as string).getTime(),
  );
  const unplaced = items.filter((item) => item.state !== "placed");

  if (items.length === 0) return null;

  return (
    <section aria-label="计划时间线" className="mt-4">
      <h4 className="mb-3 text-sm font-semibold text-slate-200">安排预览</h4>
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
      {unplaced.length > 0 && <div className="mt-4 border-t border-white/10 pt-3">
        <p className="text-xs font-semibold text-amber-200">未安排 · {unplaced.length} 项</p>
        <ul className="mt-2 space-y-2">{unplaced.map((item, index) => <li key={`${item.task_id}-${index}`} className="text-sm text-slate-200"><span>{taskTitles.get(item.task_id ?? "") ?? "任务"}</span><p className="mt-1 text-xs text-slate-400">暂时没有合适的安排位置；你可以调整计划范围或任务。</p></li>)}</ul>
      </div>}
    </section>
  );
}
