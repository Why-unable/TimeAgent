import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ActionProposal } from "../src/api/action-proposals";
import { ApprovalCard } from "../src/components/approvals/approval-card";

const proposal: ActionProposal = {
  id: "11111111-1111-4111-8111-111111111111",
  conversation_id: "22222222-2222-4222-8222-222222222222",
  agent_run_id: "33333333-3333-4333-8333-333333333333",
  original_request: "明天下午三点创建项目评审日程",
  explanation: "创建正式日程会占用你的日历时间，需要确认后执行。",
  action_type: "create_event",
  action_payload: {
    title: "项目评审",
    start_at: "2026-07-20T07:00:00Z",
    end_at: "2026-07-20T08:00:00Z",
    timezone: "Asia/Shanghai",
  },
  original_payload: {},
  display_context: { allowed_decisions: ["approve", "edit", "reject"] },
  risk_level: "high",
  status: "awaiting_approval",
  requires_approval: true,
  version: 1,
  expires_at: "2026-07-20T08:00:00Z",
  decided_at: null,
  approved_at: null,
  resumed_at: null,
  executed_at: null,
  decision_reason: "",
  execution_result: null,
  error: "",
  created_at: "2026-07-19T08:00:00Z",
  updated_at: "2026-07-19T08:00:00Z",
};

describe("ApprovalCard", () => {
  it("shows structured risk details and approves explicitly", async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    render(<ApprovalCard proposal={proposal} onDecision={onDecision} />);

    expect(screen.getByText("高风险操作")).toBeInTheDocument();
    expect(screen.getByText(proposal.original_request)).toBeInTheDocument();
    expect(screen.getAllByText(/项目评审/).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "批准" }));

    expect(onDecision).toHaveBeenCalledWith("approve", undefined);
  });

  it("allows editing arguments before approval", async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    render(<ApprovalCard proposal={proposal} onDecision={onDecision} />);

    await userEvent.click(screen.getByRole("button", { name: "调整后批准" }));
    const editor = screen.getByLabelText("日程标题");
    fireEvent.change(editor, { target: { value: "新标题" } });
    await userEvent.click(screen.getByRole("button", { name: "保存修改并批准" }));

    expect(onDecision).toHaveBeenCalledWith(
      "edit",
      expect.objectContaining({ actionPayload: expect.objectContaining({ title: "新标题" }) }),
    );
  });

  it("does not allow changing the target of a cancellation proposal", () => {
    const cancellation: ActionProposal = {
      ...proposal,
      action_type: "cancel_event",
      explanation: "取消日程会移除既有日历占用，需要确认后执行。",
      action_payload: {
        event_id: "44444444-4444-4444-8444-444444444444",
        expected_version: 3,
      },
      display_context: {
        allowed_decisions: ["approve", "reject"],
        object_name: "项目评审",
        impact_scope: "Cancels one existing calendar event",
      },
    };

    render(<ApprovalCard proposal={cancellation} onDecision={vi.fn()} />);

    expect(screen.getByText("取消日程")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "批准" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "拒绝" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑后批准" })).not.toBeInTheDocument();
    expect(screen.queryByText(/冲突检查/)).not.toBeInTheDocument();
  });

  it("lets a recurring-event proposal preview every occurrence", async () => {
    const recurring: ActionProposal = {
      ...proposal,
      action_type: "create_recurring_event",
      action_payload: {
        title: "随便学点",
        time: {
          kind: "absolute",
          start_at: "2026-07-25T10:00:00+08:00",
          end_at: "2026-07-25T10:30:00+08:00",
        },
        frequency: "daily",
        occurrence_count: 3,
      },
      display_context: {
        allowed_decisions: ["approve", "reject"],
        occurrences: [
          { index: 1, start_at: "2026-07-25T10:00:00+08:00", end_at: "2026-07-25T10:30:00+08:00", conflicts: [] },
          { index: 2, start_at: "2026-07-26T10:00:00+08:00", end_at: "2026-07-26T10:30:00+08:00", conflicts: [] },
          { index: 3, start_at: "2026-07-27T10:00:00+08:00", end_at: "2026-07-27T10:30:00+08:00", conflicts: [] },
        ],
      },
    };

    render(<ApprovalCard proposal={recurring} onDecision={vi.fn()} />);

    expect(screen.getByText(/第 1 \/ 3 次/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "查看下一个日程实例" }));
    expect(screen.getByText(/第 2 \/ 3 次/)).toBeInTheDocument();
  });
});
