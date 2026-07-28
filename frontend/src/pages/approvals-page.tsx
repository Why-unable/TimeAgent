import { ShieldCheck } from "lucide-react";
import { useState } from "react";

import type { ActionProposalStatus } from "../api/action-proposals";
import { ApprovalCard } from "../components/approvals/approval-card";
import { useActionProposals, useProposalDecision } from "../features/approvals/hooks";
import { useCurrentUser } from "../features/accounts/hooks";

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
  const [filter, setFilter] = useState<ActionProposalStatus | undefined>("awaiting_approval");
  const proposals = useActionProposals(filter);
  const decision = useProposalDecision();
  const visibleProposals = currentUser.data?.is_staff || filter === "awaiting_approval"
    ? proposals.data ?? []
    : (proposals.data ?? []).slice(0, 10);

  return (
    <section className="mx-auto max-w-5xl">
      <div className="mt-2 flex items-center gap-3">
        <ShieldCheck className="text-cyan-300" />
        <h2 className="text-3xl font-semibold">操作审批</h2>
      </div>
      <p className="mt-3 text-slate-400">审查、编辑或拒绝 Agent 提出的高风险操作。</p>

      <div className="mt-7 flex flex-wrap gap-2" role="group" aria-label="审批状态筛选">
        {filters.map((item) => (
          <button key={item.label} type="button" onClick={() => setFilter(item.value)} className={`rounded-full px-4 py-2 text-sm ${filter === item.value ? "bg-cyan-300 text-slate-950" : "bg-white/5 text-slate-300 hover:bg-white/10"}`}>{item.label}</button>
        ))}
      </div>

      <div className="mt-6 space-y-4">
        {proposals.isPending && <p className="text-slate-400">正在加载审批…</p>}
        {proposals.isError && <p role="alert" className="rounded-xl border border-red-400/30 bg-red-400/10 p-4 text-red-100">无法加载审批列表。</p>}
        {visibleProposals.length === 0 && <div className="rounded-2xl border border-dashed border-white/10 p-12 text-center text-slate-500">当前没有符合条件的操作</div>}
        {visibleProposals.map((proposal) => (
          <ApprovalCard
            key={proposal.id}
            proposal={proposal}
            busy={decision.isPending}
            onDecision={(decisionType, options) => decision.mutateAsync({ proposal, decision: decisionType, actionPayload: options?.actionPayload, reason: options?.reason })}
          />
        ))}
      </div>
    </section>
  );
}
