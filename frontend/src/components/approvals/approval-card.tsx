import { Check, Clock3, Pencil, ShieldAlert, X } from "lucide-react";
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

export function ApprovalCard({ proposal, busy = false, onDecision }: ApprovalCardProps) {
  const [editing, setEditing] = useState(false);
  const [payloadText, setPayloadText] = useState(() =>
    JSON.stringify(proposal.action_payload, null, 2),
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const awaiting = proposal.status === "awaiting_approval";
  const conflicts = Array.isArray(proposal.display_context.conflicts)
    ? proposal.display_context.conflicts
    : [];
  const allowedDecisions = Array.isArray(proposal.display_context.allowed_decisions)
    ? proposal.display_context.allowed_decisions
    : [];
  const canApprove = allowedDecisions.includes("approve");
  const canEdit = allowedDecisions.includes("edit");
  const canReject = allowedDecisions.includes("reject");
  const showsConflictCheck = "conflict_check" in proposal.display_context;

  const submitEdit = async () => {
    try {
      const parsed = JSON.parse(payloadText) as unknown;
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("操作参数必须是 JSON 对象");
      }
      setError("");
      await onDecision("edit", { actionPayload: parsed as Record<string, unknown> });
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
          <textarea
            aria-label="编辑操作参数"
            rows={10}
            value={payloadText}
            onChange={(event) => setPayloadText(event.target.value)}
            className="mt-2 w-full rounded-lg border border-white/10 bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-200 outline-none focus:border-amber-300/50"
          />
        ) : (
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-xs leading-5 text-cyan-100">
            {JSON.stringify(proposal.action_payload, null, 2)}
          </pre>
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
              <button type="button" onClick={() => setEditing(false)} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300">取消编辑</button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {canApprove && <button type="button" disabled={busy} onClick={() => void submitDecision("approve")} className="inline-flex items-center gap-2 rounded-lg bg-emerald-300 px-4 py-2 text-sm font-medium text-slate-950 disabled:opacity-50"><Check size={16} />批准</button>}
              {canEdit && <button type="button" disabled={busy} onClick={() => setEditing(true)} className="inline-flex items-center gap-2 rounded-lg border border-amber-300/30 px-4 py-2 text-sm text-amber-100 disabled:opacity-50"><Pencil size={16} />编辑后批准</button>}
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
