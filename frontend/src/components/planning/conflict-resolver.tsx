import { formatTimeInUserTimezone } from "../../utils/datetime";

type Conflict = { kind: string; label: string; start_at: string; end_at: string };
type Candidate = { start_at: string; end_at: string };

const reasonLabels: Record<string, string> = {
  schedule_conflict: "与现有日程或任务时间冲突",
  work_hours_violation: "超出你的工作时段",
  deadline_violation: "超过任务截止时间",
  max_daily_minutes_violation: "超过每日可安排时长",
  planning_exact_start_violation: "不符合指定的准确开始时间",
  planning_dependency_order_violation: "违反任务依赖顺序",
  plan_item_locked: "该时间块已固定，请先解锁",
  task_version_changed: "任务在计划创建后发生了变化",
  schedule_in_past: "不能把任务安排在过去",
};

export function ConflictResolver({
  timezone,
  reasonCodes,
  conflicts,
  candidate,
  onUseCandidate,
}: {
  timezone: string;
  reasonCodes: string[];
  conflicts: Conflict[];
  candidate: Candidate | null;
  onUseCandidate: () => void;
}) {
  return (
    <section aria-label="时间冲突与可选安排" className="mt-3 rounded-xl border border-amber-300/30 bg-amber-300/5 p-3 text-xs text-amber-50">
      <h5 className="font-semibold">这个时间暂时不可用</h5>
      {reasonCodes.map((code) => <p key={code} className="mt-1">{reasonLabels[code] ?? code.replaceAll("_", " ")}</p>)}
      {conflicts.map((conflict, index) => (
        <p key={`${conflict.kind}-${index}`} className="mt-2 rounded-lg bg-black/10 p-2">
          {conflict.label} · {formatTimeInUserTimezone(conflict.start_at, timezone)}–{formatTimeInUserTimezone(conflict.end_at, timezone)}
        </p>
      ))}
      {candidate && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <p>后端检查过的可选时间：{formatTimeInUserTimezone(candidate.start_at, timezone)}–{formatTimeInUserTimezone(candidate.end_at, timezone)}</p>
          <button type="button" onClick={onUseCandidate} className="min-h-11 rounded-lg bg-amber-100 px-3 font-semibold text-slate-950">使用这个时间</button>
        </div>
      )}
    </section>
  );
}
