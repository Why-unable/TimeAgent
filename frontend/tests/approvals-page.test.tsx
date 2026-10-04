import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

const mocks = vi.hoisted(() => ({
  useActionProposals: vi.fn(),
  useProposalDecision: vi.fn(),
  useCurrentUser: vi.fn(),
  useCurrentUserPreference: vi.fn(),
}));

vi.mock("../src/features/approvals/hooks", () => ({
  useActionProposals: mocks.useActionProposals,
  useProposalDecision: mocks.useProposalDecision,
}));
vi.mock("../src/features/accounts/hooks", () => ({ useCurrentUser: mocks.useCurrentUser }));
vi.mock("../src/features/preferences/hooks", () => ({
  useCurrentUserPreference: mocks.useCurrentUserPreference,
}));
vi.mock("../src/components/approvals/approval-card", () => ({
  ApprovalCard: ({
    onDecision,
  }: {
    onDecision: (decision: "approve" | "edit" | "reject") => Promise<unknown>;
  }) => (
    <div>
      <button type="button" onClick={() => void onDecision("approve")}>模拟批准</button>
      <button type="button" onClick={() => void onDecision("edit")}>模拟编辑</button>
    </div>
  ),
}));

import { ApprovalsPage } from "../src/pages/approvals-page";

const proposal = {
  id: "44444444-4444-4444-8444-444444444444",
  conversation_id: "55555555-5555-4555-8555-555555555555",
  agent_run_id: "66666666-6666-4666-8666-666666666666",
  original_request: "移动任务",
  explanation: "需要确认日程变更",
  action_type: "apply_schedule_plan",
  action_payload: {},
  original_payload: {},
  display_context: {},
  risk_level: "high" as const,
  status: "awaiting_approval" as const,
  requires_approval: true,
  version: 1,
  expires_at: "2026-10-03T12:00:00Z",
  decided_at: null,
  approved_at: null,
  resumed_at: null,
  executed_at: null,
  decision_reason: "",
  execution_result: null,
  error: "",
  created_at: "2026-10-03T11:00:00Z",
  updated_at: "2026-10-03T11:00:00Z",
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <ApprovalsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("ApprovalsPage", () => {
  beforeEach(() => {
    mocks.useActionProposals.mockReturnValue({ data: [proposal], isPending: false, isError: false });
    mocks.useProposalDecision.mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn(async ({ decision }: { decision: "approve" | "edit" | "reject" }) => ({
        proposal: {
          ...proposal,
          status: decision === "edit" ? "awaiting_approval" : "executed",
        },
        resume_queued: false,
      })),
    });
    mocks.useCurrentUser.mockReturnValue({ data: { is_staff: false } });
    mocks.useCurrentUserPreference.mockReturnValue({ data: { timezone: "Asia/Shanghai" } });
  });

  it("announces and focuses every repeated decision with an accurate result", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "模拟批准" }));
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("第 1 项操作已完成");
    expect(status).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "模拟批准" }));
    expect(status).toHaveTextContent("第 2 项操作已完成");
    expect(status).toHaveFocus();
  });

  it("uses a mobile status drawer and applies the selected filter", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /状态：等待审批/ }));
    const dialog = screen.getByRole("dialog", { name: "筛选审批状态" });
    await user.click(within(dialog).getByRole("button", { name: "已执行" }));

    expect(mocks.useActionProposals).toHaveBeenLastCalledWith("executed");
    expect(screen.queryByRole("dialog", { name: "筛选审批状态" })).not.toBeInTheDocument();
  });

  it("offers a retry instead of showing an empty list after a load failure", async () => {
    const refetch = vi.fn();
    mocks.useActionProposals.mockReturnValue({ data: undefined, isPending: false, isError: true, isSuccess: false, refetch });
    renderPage();

    expect(screen.getByRole("alert")).toHaveTextContent("无法加载审批列表");
    expect(screen.queryByText("当前没有符合条件的操作")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "重试读取" }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("keeps an edited proposal described as awaiting approval", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "模拟编辑" }));

    expect(screen.getByRole("status")).toHaveTextContent("审批内容已更新，仍待审批");
    expect(screen.getByRole("status")).toHaveFocus();
  });

  it("announces a refreshed plan as still awaiting review", async () => {
    mocks.useProposalDecision.mockReturnValue({
      isPending: false,
      mutateAsync: vi.fn(async () => ({
        proposal: { ...proposal, action_type: "apply_schedule_plan", status: "awaiting_approval" },
        resume_queued: false,
      })),
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "模拟批准" }));

    expect(screen.getByRole("status")).toHaveTextContent("计划已有更新，仍待审批");
    expect(screen.getByRole("status")).toHaveFocus();
  });
});
