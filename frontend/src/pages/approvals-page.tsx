import { ChevronDown, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { ActionProposalStatus } from "../api/action-proposals";
import { ApprovalCard } from "../components/approvals/approval-card";
import { useActionProposals, useProposalDecision } from "../features/approvals/hooks";
import { useCurrentUser } from "../features/accounts/hooks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import { Drawer } from "../components/overlay/drawer";

const filters: { value: ActionProposalStatus | undefined; label: string }[] = [
  { value: undefined, label: "全部" },
  { value: "awaiting_approval", label: "等待审批" },
  { value: "executed", label: "已执行" },
  { value: "rejected", label: "已拒绝" },
  { value: "expired", label: "已过期" },
  { value: "failed", label: "执行失败" },
];

export function ApprovalsPage() {
  const currentUser = useCurrentUser();
  const preference = useCurrentUserPreference();
  const timezone = preference.data?.timezone ?? import.meta.env.VITE_DEFAULT_TIMEZONE ?? "Asia/Shanghai";
  const [filter, setFilter] = useState<ActionProposalStatus | undefined>("awaiting_approval");
  const [decisionNotice, setDecisionNotice] = useState("");
  const [decisionCount, setDecisionCount] = useState(0);
  const [filterOpen, setFilterOpen] = useState(false);
  const decisionNoticeRef = useRef<HTMLParagraphElement>(null);
  const proposals = useActionProposals(filter);
  const decision = useProposalDecision();
  const visibleProposals = currentUser.data?.is_staff || filter === "awaiting_approval"
    ? proposals.data ?? []
    : (proposals.data ?? []).slice(0, 10);
  const selectedFilter = filters.find((item) => item.value === filter) ?? filters[1];

  useEffect(() => {
    if (decisionNotice) decisionNoticeRef.current?.focus();
  }, [decisionNotice]);

  const submitDecision = async (
    proposal: (typeof visibleProposals)[number],
    decisionType: "approve" | "edit" | "reject",
    options?: { actionPayload?: Record<string, unknown>; reason?: string },
  ) => {
    const result = await decision.mutateAsync({
      proposal,
      decision: decisionType,
      actionPayload: options?.actionPayload,
      reason: options?.reason,
    });
    const nextDecisionCount = decisionCount + 1;
    setDecisionCount(nextDecisionCount);
    const sequence = `第 ${nextDecisionCount} 项`;
    const notice = decisionType === "reject"
      ? `${sequence}操作已拒绝，列表已更新。`
      : decisionType === "edit"
        ? result.proposal.status === "awaiting_approval"
          ? `${sequence}审批内容已更新，仍待审批，请核对最新内容。`
          : `${sequence}审批内容已更新，列表已刷新。`
        : result.proposal.status === "executed"
          ? `${sequence}操作已完成，列表已更新。`
          : result.proposal.status === "failed"
            ? `${sequence}审批已处理，但执行失败，请检查结果。`
            : result.proposal.status === "awaiting_approval"
              ? result.proposal.action_type === "apply_schedule_plan"
                ? `${sequence}计划已有更新，仍待审批，请核对最新安排。`
                : `${sequence}操作信息已更新，仍待审批，请核对最新内容。`
              : result.proposal.status === "approved" || result.proposal.status === "executing"
                ? `${sequence}审批已提交，操作仍在处理中。`
                : `${sequence}审批状态已更新，请核对当前状态。`;
    setDecisionNotice(notice);
    return result;
  };

  return (
    <section className="mx-auto max-w-5xl">
      <div className="mt-2 flex items-center gap-3">
        <ShieldCheck className="shrink-0 text-teal-700" />
        <h2 className="text-2xl font-semibold text-slate-900 lg:text-3xl">操作审批</h2>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-700 lg:text-slate-400">这里列出需要你确认的更改。请先查看影响，再决定是否继续。</p>
      <p className="mt-2 text-sm text-slate-600">以下时间均按 {timezone} 显示。</p>
      <p ref={decisionNoticeRef} tabIndex={-1} role="status" aria-live="polite" className="sr-only">{decisionNotice}</p>

      <div className="mt-5 flex items-center gap-3 lg:hidden">
        <button type="button" onClick={() => setFilterOpen(true)} className="inline-flex min-h-12 flex-1 items-center justify-between rounded-xl border border-slate-300 bg-white px-4 text-left font-medium text-slate-900">
          <span>状态：{selectedFilter.label}</span><ChevronDown size={18} aria-hidden="true" />
        </button>
        <span className="shrink-0 text-sm text-slate-600">{proposals.data?.length ?? 0} 项</span>
      </div>
      <div className="mt-7 hidden flex-wrap gap-2 lg:flex" role="group" aria-label="审批状态筛选">
        {filters.map((item) => (
          <button
            key={item.label}
            type="button"
            aria-pressed={filter === item.value}
            onClick={() => setFilter(item.value)}
            className={`min-h-11 rounded-full px-4 py-2 text-sm ${filter === item.value ? "bg-cyan-300 text-slate-950" : "bg-white/5 text-slate-300 hover:bg-white/10"}`}
          >
            {item.label}
          </button>
        ))}
      </div>
      {filterOpen && <Drawer title="筛选审批状态" description="选择要查看的操作状态。" onClose={() => setFilterOpen(false)}>
        <div className="grid gap-2" role="group" aria-label="审批状态筛选">
          {filters.map((item) => <button key={item.label} type="button" aria-pressed={filter === item.value} onClick={() => { setFilter(item.value); setFilterOpen(false); }} className={`min-h-12 rounded-xl border px-4 text-left font-medium ${filter === item.value ? "border-teal-700 bg-teal-50 text-teal-900" : "border-slate-200 bg-white text-slate-800"}`}>{item.label}</button>)}
        </div>
      </Drawer>}

      <div className="mt-6 space-y-4">
        {proposals.isPending && <p role="status" className="text-slate-600">正在加载审批…</p>}
        {proposals.isError && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 p-4 text-red-950"><p>无法加载审批列表。</p><button type="button" onClick={() => void proposals.refetch()} className="mt-2 inline-flex min-h-11 items-center font-medium underline underline-offset-2">重试读取</button></div>}
        {proposals.isSuccess && visibleProposals.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-slate-600">当前没有符合条件的操作</div>}
        {visibleProposals.map((proposal) => (
          <ApprovalCard
            key={proposal.id}
            proposal={proposal}
            timezone={timezone}
            busy={decision.isPending}
            onDecision={(decisionType, options) => submitDecision(proposal, decisionType, options)}
          />
        ))}
      </div>
    </section>
  );
}
