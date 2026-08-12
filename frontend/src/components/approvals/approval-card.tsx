import { Check, ChevronLeft, ChevronRight, Clock3, Pencil, ShieldAlert, X } from "lucide-react";
import { useState } from "react";

import type { ActionProposal, ProposalDecisionResponse } from "../../api/action-proposals";

const statusLabels = {
  awaiting_approval: "等待审批",
  approved: "已批准，等待执行",
  rejected: "已拒绝",
  executing: "正在执行",
  executed: "已执行",
  failed: "执行失败",
  expired: "已过期",
} as const;

const actionLabels: Record<string, string> = {
  create_recurring_event: "创建重复日程",
  mutate_events: "批量调整日程",
  create_event: "创建日程",
  cancel_event: "取消日程",
  cancel_reminder: "取消提醒",
  cancel_task: "取消任务",
};

interface ApprovalCardProps {
  proposal: ActionProposal;
  busy?: boolean;
  onDecision: (
    decision: "approve" | "edit" | "reject",
    options?: { actionPayload?: Record<string, unknown>; reason?: string },
  ) => Promise<ProposalDecisionResponse | void>;
}

interface RecurringOccurrencePreview {
  index: number;
  start_at: string;
  end_at: string;
  conflicts: unknown[];
}

function recurringOccurrencePreviews(value: unknown): RecurringOccurrencePreview[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const preview = item as Record<string, unknown>;
    if (
      typeof preview.index !== "number" ||
      typeof preview.start_at !== "string" ||
      typeof preview.end_at !== "string"
    ) return [];
    return [{
      index: preview.index,
      start_at: preview.start_at,
      end_at: preview.end_at,
      conflicts: Array.isArray(preview.conflicts) ? preview.conflicts : [],
    }];
  });
}

function recurringOccurrencePreviewsFromPayload(
  actionType: string,
  payload: Record<string, unknown>,
): RecurringOccurrencePreview[] {
  if (actionType !== "create_recurring_event") return [];
  const time = payload.time && typeof payload.time === "object"
    ? payload.time as Record<string, unknown>
    : payload;
  const startAt = typeof time.start_at === "string" ? new Date(time.start_at) : null;
  const endAt = typeof time.end_at === "string" ? new Date(time.end_at) : null;
  const frequency = typeof payload.frequency === "string" ? payload.frequency : "daily";
  const occurrenceCount = Number(payload.occurrence_count);
  const interval = Number(payload.interval ?? 1);
  if (
    !startAt || !endAt || Number.isNaN(startAt.getTime()) || Number.isNaN(endAt.getTime())
    || !Number.isInteger(occurrenceCount) || occurrenceCount < 1
    || !Number.isInteger(interval) || interval < 1
  ) return [];

  const duration = endAt.getTime() - startAt.getTime();
  const current = new Date(startAt);
  return Array.from({ length: occurrenceCount }, (_, offset) => {
    const occurrence = {
      index: offset + 1,
      start_at: current.toISOString(),
      end_at: new Date(current.getTime() + duration).toISOString(),
      conflicts: [],
    };
    if (frequency === "weekly") current.setUTCDate(current.getUTCDate() + 7 * interval);
    else if (frequency === "monthly") current.setUTCMonth(current.getUTCMonth() + interval);
    else current.setUTCDate(current.getUTCDate() + interval);
    return occurrence;
  });
}

function formatOccurrenceTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function toDateTimeLocal(value: unknown): string {
  if (typeof value !== "string") return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function keepTimezoneOffset(original: unknown, localValue: string): string {
  if (!localValue) return localValue;
  if (typeof original !== "string") return localValue;
  const offset = original.match(/(Z|[+-]\d{2}:\d{2})$/)?.[1];
  return `${localValue}${offset ?? ""}`;
}

function resolvedReviewPayload(proposal: ActionProposal): Record<string, unknown> {
  const payload = { ...proposal.action_payload };
  if (proposal.action_type === "mutate_events") {
    const resolved = proposal.display_context.resolved_operations;
    if (Array.isArray(resolved) && resolved.length > 0) {
      return { ...payload, operations: resolved };
    }
  }
  if (proposal.action_type === "create_recurring_event") {
    const occurrences = recurringOccurrencePreviews(proposal.display_context.occurrences);
    if (occurrences.length > 0) {
      return {
        ...payload,
        time: {
          kind: "absolute",
          start_at: occurrences[0].start_at,
          end_at: occurrences[0].end_at,
        },
      };
    }
  }
  return payload;
}

function PayloadSummary({ actionType, payload }: { actionType: string; payload: Record<string, unknown> }) {
  const operations = Array.isArray(payload.operations) ? payload.operations : [];
  const time = payload.time && typeof payload.time === "object"
    ? payload.time as Record<string, unknown>
    : payload;
  if (actionType === "mutate_events") {
    return (
      <div className="space-y-2">
        {operations.map((item, index) => {
          const operation = item as Record<string, unknown>;
          return <p key={index} className="rounded-lg bg-slate-950/60 px-3 py-2 text-sm text-slate-200">{`${index + 1}. ${String(operation.action ?? "调整")}：${String(operation.title ?? "已有日程")}`}</p>;
        })}
      </div>
    );
  }
  return (
    <div className="grid gap-2 text-sm text-slate-200 sm:grid-cols-2">
      <p><span className="text-slate-500">标题：</span>{String(payload.title ?? "未命名日程")}</p>
      {typeof time.start_at === "string" && <p><span className="text-slate-500">开始：</span>{formatOccurrenceTime(time.start_at)}</p>}
      {typeof time.end_at === "string" && <p><span className="text-slate-500">结束：</span>{formatOccurrenceTime(time.end_at)}</p>}
      {actionType === "create_recurring_event" && <p><span className="text-slate-500">重复：</span>{String(payload.frequency ?? "daily")}，共 {String(payload.occurrence_count ?? 1)} 次</p>}
    </div>
  );
}

function ApprovalEditor({
  actionType,
  payload,
  onChange,
}: {
  actionType: string;
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const setField = (field: string, value: unknown) => onChange({ ...payload, [field]: value });
  const inputClass = "mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-300/50";
  if (actionType === "mutate_events") {
    const operations = Array.isArray(payload.operations) ? payload.operations : [];
    const setOperation = (index: number, field: string, value: unknown) => {
      const next = operations.map((item, current) => current === index
        ? { ...(item as Record<string, unknown>), [field]: value }
        : item);
      setField("operations", next);
    };
    const setOperationTime = (index: number, field: "start_at" | "end_at", value: string) => {
      const operation = operations[index] as Record<string, unknown>;
      const time = operation.time && typeof operation.time === "object"
        ? operation.time as Record<string, unknown>
        : {};
      setOperation(index, "time", { ...time, kind: "absolute", [field]: value });
    };
    return (
      <div className="space-y-3">
        {operations.map((item, index) => {
          const operation = item as Record<string, unknown>;
          const action = String(operation.action ?? "update");
          const time = operation.time && typeof operation.time === "object"
            ? operation.time as Record<string, unknown>
            : {};
          return (
            <fieldset key={index} className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
              <legend className="px-1 text-xs font-medium text-cyan-200">第 {index + 1} 项：{action}</legend>
              {action !== "cancel" && <label className="block text-xs text-slate-400">日程标题<input value={String(operation.title ?? "")} onChange={(event) => setOperation(index, "title", event.target.value)} className={inputClass} /></label>}
              {action !== "cancel" && <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <label className="text-xs text-slate-400">开始时间<input type="datetime-local" value={toDateTimeLocal(time.start_at)} onChange={(event) => setOperationTime(index, "start_at", keepTimezoneOffset(time.start_at, event.target.value))} className={inputClass} /></label>
                <label className="text-xs text-slate-400">结束时间<input type="datetime-local" value={toDateTimeLocal(time.end_at)} onChange={(event) => setOperationTime(index, "end_at", keepTimezoneOffset(time.end_at, event.target.value))} className={inputClass} /></label>
              </div>}
            </fieldset>
          );
        })}
      </div>
    );
  }
  const time = payload.time && typeof payload.time === "object"
    ? payload.time as Record<string, unknown>
    : payload;
  const setTime = (field: "start_at" | "end_at", value: string) => {
    if (payload.time && typeof payload.time === "object") {
      setField("time", { ...time, kind: "absolute", [field]: value });
    } else {
      setField(field, value);
    }
  };
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="sm:col-span-2 text-xs text-slate-400">日程标题<input value={String(payload.title ?? "")} onChange={(event) => setField("title", event.target.value)} className={inputClass} /></label>
      <label className="text-xs text-slate-400">开始时间<input type="datetime-local" value={toDateTimeLocal(time.start_at)} onChange={(event) => setTime("start_at", keepTimezoneOffset(time.start_at, event.target.value))} className={inputClass} /></label>
      <label className="text-xs text-slate-400">结束时间<input type="datetime-local" value={toDateTimeLocal(time.end_at)} onChange={(event) => setTime("end_at", keepTimezoneOffset(time.end_at, event.target.value))} className={inputClass} /></label>
      {actionType === "create_recurring_event" && <>
        <label className="text-xs text-slate-400">重复频率<select value={String(payload.frequency ?? "daily")} onChange={(event) => setField("frequency", event.target.value)} className={inputClass}><option value="daily">每天</option><option value="weekly">每周</option><option value="monthly">每月</option></select></label>
        <label className="text-xs text-slate-400">重复次数<input type="number" min="1" value={String(payload.occurrence_count ?? 1)} onChange={(event) => setField("occurrence_count", Number(event.target.value))} className={inputClass} /></label>
      </>}
    </div>
  );
}

export function ApprovalCard({ proposal, busy = false, onDecision }: ApprovalCardProps) {
  const [editing, setEditing] = useState(false);
  const [editedPayload, setEditedPayload] = useState<Record<string, unknown>>(
    () => resolvedReviewPayload(proposal),
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [occurrenceIndex, setOccurrenceIndex] = useState(0);
  const awaiting = proposal.status === "awaiting_approval";
  const conflicts = Array.isArray(proposal.display_context.conflicts)
    ? proposal.display_context.conflicts
    : [];
  const allowedDecisions = Array.isArray(proposal.display_context.allowed_decisions)
    ? proposal.display_context.allowed_decisions
    : [];
  const canApprove = allowedDecisions.includes("approve");
  const canEdit = allowedDecisions.includes("edit") && [
    "create_event",
    "update_event",
    "create_recurring_event",
    "mutate_events",
  ].includes(proposal.action_type);
  const canReject = allowedDecisions.includes("reject");
  const showsConflictCheck = "conflict_check" in proposal.display_context;
  const occurrences = recurringOccurrencePreviews(proposal.display_context.occurrences);
  const fallbackOccurrences = recurringOccurrencePreviewsFromPayload(
    proposal.action_type,
    proposal.action_payload,
  );
  const displayedOccurrences = occurrences.length > 0 ? occurrences : fallbackOccurrences;
  const selectedOccurrence = displayedOccurrences[
    Math.min(occurrenceIndex, Math.max(displayedOccurrences.length - 1, 0))
  ];

  const submitEdit = async () => {
    try {
      if (
        ["create_event", "create_recurring_event"].includes(proposal.action_type)
        && !editedPayload.title
      ) {
        throw new Error("请填写日程标题");
      }
      setError("");
      await onDecision("edit", { actionPayload: editedPayload });
      setEditing(false);
    } catch (reasonValue) {
      setError(reasonValue instanceof Error ? reasonValue.message : "参数格式不正确");
    }
  };

  const submitDecision = async (decision: "approve" | "reject") => {
    try {
      setError("");
      await onDecision(decision, decision === "reject" ? { reason } : undefined);
    } catch (reasonValue) {
      setError(reasonValue instanceof Error ? reasonValue.message : "审批提交失败");
    }
  };

  return (
    <article className="rounded-2xl border border-amber-300/25 bg-amber-300/5 p-5 shadow-lg shadow-black/10">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex gap-3">
          <span className="rounded-xl bg-amber-300/10 p-2 text-amber-200"><ShieldAlert size={20} /></span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-amber-200">高风险操作</p>
            <h3 className="mt-1 font-semibold text-slate-100">
              {actionLabels[proposal.action_type] ?? proposal.action_type}
            </h3>
          </div>
        </div>
        <span className="rounded-full bg-white/5 px-3 py-1 text-xs text-slate-300">
          {statusLabels[proposal.status]}
        </span>
      </div>

      <p className="mt-4 text-sm leading-6 text-slate-300">{proposal.explanation}</p>
      {selectedOccurrence && (
        <section className="relative mt-4 rounded-xl border border-cyan-300/20 bg-cyan-300/5 px-12 py-4" aria-label="周期日程实例预览">
          <button
            type="button"
            aria-label="查看上一个日程实例"
            disabled={occurrenceIndex === 0}
            onClick={() => setOccurrenceIndex((current) => Math.max(0, current - 1))}
            className="absolute inset-y-0 left-1 grid w-10 place-items-center text-cyan-200 disabled:text-slate-700"
          >
            <ChevronLeft size={26} />
          </button>
          <div className="text-center">
            <p className="text-xs font-medium text-cyan-200">周期日程 · 第 {selectedOccurrence.index} / {displayedOccurrences.length} 次</p>
            <p className="mt-2 text-base font-semibold text-slate-100">{formatOccurrenceTime(selectedOccurrence.start_at)} — {new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(selectedOccurrence.end_at))}</p>
            <p className={`mt-1 text-xs ${selectedOccurrence.conflicts.length > 0 ? "text-red-200" : "text-emerald-200"}`}>
              {selectedOccurrence.conflicts.length > 0 ? `此实例有 ${selectedOccurrence.conflicts.length} 个时间冲突` : "此实例暂无时间冲突"}
            </p>
          </div>
          <button
            type="button"
            aria-label="查看下一个日程实例"
            disabled={occurrenceIndex >= displayedOccurrences.length - 1}
            onClick={() => setOccurrenceIndex((current) => Math.min(displayedOccurrences.length - 1, current + 1))}
            className="absolute inset-y-0 right-1 grid w-10 place-items-center text-cyan-200 disabled:text-slate-700"
          >
            <ChevronRight size={26} />
          </button>
        </section>
      )}
      <dl className="mt-4 grid gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm sm:grid-cols-2">
        <div><dt className="text-xs text-slate-500">对象名称</dt><dd className="mt-1 text-slate-200">{String(proposal.display_context.object_name || proposal.action_payload.title || "未命名操作")}</dd></div>
        <div><dt className="text-xs text-slate-500">影响范围</dt><dd className="mt-1 text-slate-200">{String(proposal.display_context.impact_scope || "单项操作")}</dd></div>
        <div><dt className="text-xs text-slate-500">拟开始时间</dt><dd className="mt-1 text-slate-200">{String(proposal.display_context.proposed_start_at || "—")}</dd></div>
        <div><dt className="text-xs text-slate-500">拟结束时间</dt><dd className="mt-1 text-slate-200">{String(proposal.display_context.proposed_end_at || "—")}</dd></div>
        <div><dt className="text-xs text-slate-500">提出时间</dt><dd className="mt-1 text-slate-200">{new Date(proposal.created_at).toLocaleString("zh-CN")}</dd></div>
        <div><dt className="text-xs text-slate-500">重复操作</dt><dd className="mt-1 text-slate-200">{proposal.display_context.is_recurring ? "是" : "否"}</dd></div>
      </dl>
      {showsConflictCheck && (
        <div className={`mt-3 rounded-xl border p-3 text-sm ${conflicts.length > 0 ? "border-red-300/25 bg-red-300/5 text-red-100" : "border-emerald-300/15 bg-emerald-300/5 text-emerald-100"}`}>
          {conflicts.length > 0
            ? `发现 ${conflicts.length} 个时间冲突，请在批准前检查。`
            : proposal.display_context.conflict_check === "completed"
              ? "未发现日程冲突。"
              : "当前参数尚未完成冲突检查。"}
        </div>
      )}
      <div className="mt-4 rounded-xl border border-white/10 bg-slate-950/60 p-4">
        <p className="text-xs text-slate-500">用户原始请求</p>
        <p className="mt-1 text-sm text-slate-200">{proposal.original_request}</p>
        <p className="mt-4 text-xs text-slate-500">拟执行参数</p>
        {editing ? (
          <div className="mt-3">
            <ApprovalEditor
              actionType={proposal.action_type}
              payload={editedPayload}
              onChange={setEditedPayload}
            />
          </div>
        ) : (
          <div className="mt-2"><PayloadSummary actionType={proposal.action_type} payload={resolvedReviewPayload(proposal)} /></div>
        )}
      </div>

      <p className="mt-3 flex items-center gap-2 text-xs text-slate-500">
        <Clock3 size={14} /> 审批有效期至 {new Date(proposal.expires_at).toLocaleString("zh-CN")}
      </p>
      {proposal.error && <p role="alert" className="mt-3 text-sm text-red-300">{proposal.error}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}

      {awaiting && (
        <div className="mt-5">
          {editing ? (
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={busy} onClick={submitEdit} className="rounded-lg bg-amber-200 px-4 py-2 text-sm font-medium text-slate-950 disabled:opacity-50">保存修改并批准</button>
              <button type="button" onClick={() => { setEditedPayload(resolvedReviewPayload(proposal)); setEditing(false); }} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300">取消编辑</button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {canApprove && <button type="button" disabled={busy} onClick={() => void submitDecision("approve")} className="inline-flex items-center gap-2 rounded-lg bg-emerald-300 px-4 py-2 text-sm font-medium text-slate-950 disabled:opacity-50"><Check size={16} />批准</button>}
              {canEdit && <button type="button" disabled={busy} onClick={() => { setEditedPayload(resolvedReviewPayload(proposal)); setEditing(true); }} className="inline-flex items-center gap-2 rounded-lg border border-amber-300/30 px-4 py-2 text-sm text-amber-100 disabled:opacity-50"><Pencil size={16} />调整后批准</button>}
              {canReject && <button type="button" disabled={busy} onClick={() => void submitDecision("reject")} className="inline-flex items-center gap-2 rounded-lg border border-red-300/25 px-4 py-2 text-sm text-red-200 disabled:opacity-50"><X size={16} />拒绝</button>}
            </div>
          )}
          {!editing && canReject && (
            <input value={reason} onChange={(event) => setReason(event.target.value)} aria-label="拒绝原因" placeholder="拒绝原因（可选）" className="mt-3 w-full rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:border-red-300/40" />
          )}
        </div>
      )}
    </article>
  );
}
