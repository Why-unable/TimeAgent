import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as eventApi from "../src/api/events";
import * as taskApi from "../src/api/tasks";
import type { Task } from "../src/api/tasks";
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

    expect(screen.getByText("需要你确认")).toBeInTheDocument();
    expect(screen.getByText(proposal.original_request)).toBeInTheDocument();
    expect(screen.getAllByText(/项目评审/).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "确认并应用" }));

    expect(onDecision).toHaveBeenCalledWith("approve", undefined);
  });

  it("uses backend review items for task actions and never exposes unknown action names", () => {
    const taskProposal: ActionProposal = {
      ...proposal,
      action_type: "create_task_batch",
      action_payload: { tasks: [{ title: "准备答辩材料" }] },
      display_context: {
        allowed_decisions: ["approve", "reject"],
        action_title: "创建多项任务",
        action_summary: "将创建 1 个任务。",
        review_items: [{
          title: "准备答辩材料",
          detail: "优先级：高；预计用时：90 分钟",
          due_at: "2026-07-20T07:00:00Z",
        }],
      },
    };
    const { rerender } = render(<ApprovalCard proposal={taskProposal} timezone="Asia/Shanghai" onDecision={vi.fn()} />);

    expect(screen.getByText("创建多项任务")).toBeInTheDocument();
    expect(screen.getByText("准备答辩材料")).toBeInTheDocument();
    expect(screen.getByText(/截止：2026\/07\/20 15:00/)).toBeInTheDocument();
    expect(screen.queryByText("未命名日程")).not.toBeInTheDocument();

    const unknownProposal = {
      ...proposal,
      action_type: "future_internal_tool",
      display_context: { allowed_decisions: ["approve", "reject"] },
    } as ActionProposal;
    rerender(<ApprovalCard proposal={unknownProposal} onDecision={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "需要你确认的操作" })).toBeInTheDocument();
    expect(screen.queryByText("future_internal_tool")).not.toBeInTheDocument();
  });

  it("keeps a large review compact and lets the user expand every plan item", async () => {
    const planItems = Array.from({ length: 21 }, (_, index) => ({
      title: `安排任务 ${index + 1}`,
      detail: "计划安排时间",
    }));
    const planProposal: ActionProposal = {
      ...proposal,
      action_type: "apply_schedule_plan",
      action_payload: { plan_id: "44444444-4444-4444-8444-444444444444" },
      display_context: {
        allowed_decisions: ["approve", "reject"],
        action_title: "应用任务计划",
        action_summary: "将应用这份任务计划，涉及 21 个任务。",
        review_complete: true,
        review_items: planItems,
      },
    };

    render(<ApprovalCard proposal={planProposal} onDecision={vi.fn()} />);

    expect(screen.getByText("安排任务 1")).toBeInTheDocument();
    expect(screen.queryByText("安排任务 21")).not.toBeVisible();
    await userEvent.click(screen.getByText("查看其余 18 项"));
    expect(screen.getByText("安排任务 21")).toBeVisible();
    expect(screen.getByRole("button", { name: "确认并应用" })).toBeInTheDocument();
  });

  it("blocks an edited stale version and reopens with the refreshed proposal", async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    const firstVersion: ActionProposal = {
      ...proposal,
      action_type: "create_task_batch",
      action_payload: { tasks: [{ title: "初始任务", priority: "medium", estimated_minutes: 60 }] },
      display_context: { allowed_decisions: ["approve", "edit", "reject"], review_complete: true, review_items: [{ title: "初始任务" }] },
    };
    const { rerender } = render(<ApprovalCard proposal={firstVersion} onDecision={onDecision} />);

    await userEvent.click(screen.getByRole("button", { name: "调整后批准" }));
    fireEvent.change(screen.getByLabelText("任务名称"), { target: { value: "旧版本编辑" } });
    const refreshed: ActionProposal = {
      ...firstVersion,
      version: 2,
      action_payload: { tasks: [{ title: "最新任务", priority: "high", estimated_minutes: 90 }] },
      display_context: { ...firstVersion.display_context, review_items: [{ title: "最新任务" }] },
    };
    rerender(<ApprovalCard proposal={refreshed} onDecision={onDecision} />);

    expect(screen.getByRole("alert")).toHaveTextContent("旧内容不会提交");
    expect(screen.getByRole("button", { name: "保存修改并批准" })).toBeDisabled();
    expect(onDecision).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "取消编辑" }));
    await userEvent.click(screen.getByRole("button", { name: "调整后批准" }));
    expect(screen.getByLabelText("任务名称")).toHaveValue("最新任务");
    fireEvent.change(screen.getByLabelText("任务名称"), { target: { value: "重新编辑" } });
    await userEvent.click(screen.getByRole("button", { name: "保存修改并批准" }));
    expect(onDecision).toHaveBeenCalledWith("edit", expect.objectContaining({
      actionPayload: expect.objectContaining({ tasks: [{ title: "重新编辑", priority: "high", estimated_minutes: 90 }] }),
    }));
  });

  it("gives plan application failures a safe refresh-and-check recovery", () => {
    const failedPlanProposal: ActionProposal = {
      ...proposal,
      action_type: "apply_schedule_plan",
      status: "failed",
      error: "Schedule plan invalid: schedule_conflict",
      action_payload: { plan_id: "44444444-4444-4444-8444-444444444444" },
      display_context: { allowed_decisions: ["approve", "reject"] },
    };

    render(<ApprovalCard proposal={failedPlanProposal} onDecision={vi.fn()} />);

    expect(screen.getByText("这次计划应用没有成功。请核对计划状态和任务时间，再决定是否调整并重新提交。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开这份计划核对" })).toHaveAttribute(
      "href",
      "/planning?plan_id=44444444-4444-4444-8444-444444444444",
    );
    expect(screen.queryByText(/正式日程没有被修改/)).not.toBeInTheDocument();
  });

  it("keeps a refreshed plan pending and asks for another review", async () => {
    const refreshedProposal: ActionProposal = {
      ...proposal,
      action_type: "apply_schedule_plan",
      display_context: {
        ...proposal.display_context,
        review_complete: true,
        review_items: [{ title: "报告", detail: "计划安排时间" }],
        review_notice: "计划在提出审批后已有更新。已载入当前版本，请重新核对后再次确认。",
      },
    };
    const onDecision = vi.fn().mockResolvedValue({
      proposal: refreshedProposal,
      resume_queued: false,
    });
    render(<ApprovalCard proposal={refreshedProposal} onDecision={onDecision} />);

    await userEvent.click(screen.getByRole("button", { name: "确认并应用" }));

    expect(screen.getByText("计划在提出审批后已有更新。已载入当前版本，请重新核对后再次确认。")).toBeInTheDocument();
    expect(screen.getByText("计划内容已有更新，审批仍待处理；请核对上方最新预览。")).toBeInTheDocument();
  });

  it("exposes edit entry points for the approved task and reminder policies", () => {
    const editableProposals: ActionProposal[] = [
      {
        ...proposal,
        action_type: "create_task_batch",
        action_payload: { tasks: [{ title: "准备材料" }] },
        display_context: {
          allowed_decisions: ["approve", "edit", "reject"],
          review_complete: true,
          review_items: [{ title: "准备材料", detail: "优先级：普通" }],
        },
      },
      {
        ...proposal,
        action_type: "update_reminder",
        action_payload: { reminder_id: "44444444-4444-4444-8444-444444444444", title: "周报提醒" },
        display_context: {
          allowed_decisions: ["approve", "edit", "reject"],
          review_complete: true,
          review_items: [{ title: "周报提醒", detail: "通知方式：站内 → 邮件" }],
        },
      },
      {
        ...proposal,
        action_type: "set_reminder_target",
        action_payload: { reminder_id: "44444444-4444-4444-8444-444444444444", target_type: "custom" },
        display_context: {
          allowed_decisions: ["approve", "edit", "reject"],
          review_complete: true,
          review_items: [{ title: "周报提醒", detail: "关联对象：独立提醒 → 任务「准备材料」" }],
        },
      },
    ];

    for (const editableProposal of editableProposals) {
      const { unmount } = render(<ApprovalCard proposal={editableProposal} onDecision={vi.fn()} />);
      expect(screen.getByRole("button", { name: "调整后批准" })).toBeInTheDocument();
      unmount();
    }
  });

  it("lets the user edit task and reminder details before approval", async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    const taskProposal: ActionProposal = {
      ...proposal,
      action_type: "create_task_batch",
      action_payload: {
        tasks: [{ title: "准备材料", priority: "medium", estimated_minutes: 60 }],
      },
      display_context: {
        allowed_decisions: ["approve", "edit", "reject"],
        review_complete: true,
        review_items: [{ title: "准备材料", detail: "优先级：普通；预计用时：60 分钟" }],
      },
    };
    render(<ApprovalCard proposal={taskProposal} onDecision={onDecision} />);

    await userEvent.click(screen.getByRole("button", { name: "调整后批准" }));
    fireEvent.change(screen.getByLabelText("任务名称"), { target: { value: "准备最终材料" } });
    await userEvent.click(screen.getByRole("button", { name: "保存修改并批准" }));

    expect(onDecision).toHaveBeenCalledWith(
      "edit",
      expect.objectContaining({ actionPayload: expect.objectContaining({ tasks: [{ title: "准备最终材料", priority: "medium", estimated_minutes: 60 }] }) }),
    );
  });

  it("keeps an existing reminder target visible when it is no longer selectable", async () => {
    const taskId = "44444444-4444-4444-8444-444444444444";
    vi.spyOn(taskApi, "listTasks").mockResolvedValue([{
      id: taskId,
      title: "已完成任务",
      status: "completed",
    } as Task]);
    vi.spyOn(eventApi, "listEvents").mockResolvedValue([]);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onDecision = vi.fn().mockResolvedValue(undefined);
    const targetProposal: ActionProposal = {
      ...proposal,
      action_type: "set_reminder_target",
      action_payload: {
        reminder_id: "55555555-5555-4555-8555-555555555555",
        expected_version: 1,
        target_type: "task",
        target_id: taskId,
      },
      display_context: {
        allowed_decisions: ["approve", "edit", "reject"],
        review_complete: true,
        review_items: [{ title: "材料检查提醒", detail: "关联对象：任务「已完成任务」 → 任务「已完成任务」" }],
      },
    };
    render(
      <QueryClientProvider client={queryClient}>
        <ApprovalCard proposal={targetProposal} onDecision={onDecision} />
      </QueryClientProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "调整后批准" }));
    await screen.findByRole("status");
    const targetSelect = await screen.findByRole("combobox", { name: "提醒关联对象" });
    expect(targetSelect).toHaveValue(`task:${taskId}`);
    expect(screen.getByRole("status")).toHaveTextContent("当前关联对象不在可选列表中");
    await waitFor(() => expect(targetSelect).toHaveFocus());
    await userEvent.click(screen.getByRole("button", { name: "保存修改并批准" }));
    expect(onDecision).toHaveBeenCalledWith("edit", expect.objectContaining({
      actionPayload: expect.objectContaining({ target_type: "task", target_id: taskId }),
    }));
    queryClient.clear();
  });

  it("shows the conflicting event and explains the edit-and-recheck flow", async () => {
    const withConflict: ActionProposal = {
      ...proposal,
      display_context: {
        ...proposal.display_context,
        conflict_check: "completed",
        conflicts: [{
          id: "44444444-4444-4444-8444-444444444444",
          title: "客户评审",
          start_at: "2026-07-20T07:30:00Z",
          end_at: "2026-07-20T08:30:00Z",
          overlap_start_at: "2026-07-20T07:30:00Z",
          overlap_end_at: "2026-07-20T08:00:00Z",
        }],
      },
    };

    render(<ApprovalCard proposal={withConflict} timezone="Asia/Shanghai" onDecision={vi.fn()} />);

    expect(screen.getByText("发现 1 个时间冲突。请核对重叠时段，调整到无冲突时间，或拒绝这项操作。")).toBeInTheDocument();
    expect(screen.getByText("客户评审")).toBeInTheDocument();
    expect(screen.getByText("已占用：2026/07/20 15:30 – 16:30")).toBeInTheDocument();
    expect(screen.getByText("与你的提议重叠：2026/07/20 15:30 – 16:00")).toBeInTheDocument();
    expect(screen.getByText("在你确认前，这项操作不会执行。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确认并应用" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "先调整时间" })).toBeInTheDocument();
    expect(screen.getByText(/当前时间与已有日程冲突/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "先调整时间" }));
    expect(screen.getByRole("button", { name: "重新检查并批准" })).toBeInTheDocument();
    expect(screen.getByText("当前冲突信息对应原安排。保存后会重新检查；无冲突时才批准。")).toBeInTheDocument();
  });

  it("keeps malformed conflict details safe and understandable", () => {
    const malformedConflict = {
      ...proposal,
      display_context: {
        ...proposal.display_context,
        conflict_check: "completed",
        conflicts: [null, "bad entry", { title: "日程时间无效", start_at: "bad", end_at: "also bad" }],
      },
    } as unknown as ActionProposal;

    render(<ApprovalCard proposal={malformedConflict} onDecision={vi.fn()} />);

    expect(screen.getByText("发现 3 个时间冲突。请核对重叠时段，调整到无冲突时间，或拒绝这项操作。")).toBeInTheDocument();
    expect(screen.getByText("日程时间无效")).toBeInTheDocument();
    expect(screen.getByText("已占用：时间信息暂不可用")).toBeInTheDocument();
    expect(screen.getByText("部分冲突详情暂不可用。")).toBeInTheDocument();
  });

  it("exposes additional conflicts through the native disclosure", async () => {
    const conflicts = Array.from({ length: 4 }, (_, index) => ({
      id: `44444444-4444-4444-8444-44444444444${index}`,
      title: `已有安排 ${index + 1}`,
      start_at: "2026-07-20T07:30:00Z",
      end_at: "2026-07-20T08:30:00Z",
      overlap_start_at: "2026-07-20T07:30:00Z",
      overlap_end_at: "2026-07-20T08:00:00Z",
    }));
    const withManyConflicts: ActionProposal = {
      ...proposal,
      display_context: {
        ...proposal.display_context,
        conflict_check: "completed",
        conflicts,
      },
    };
    render(<ApprovalCard proposal={withManyConflicts} onDecision={vi.fn()} />);

    expect(screen.getByText("已有安排 1")).toBeVisible();
    expect(screen.getByText("已有安排 3")).toBeVisible();
    expect(screen.getByText("已有安排 4")).not.toBeVisible();
    const disclosure = screen.getByText("查看其余 1 个冲突");
    await userEvent.click(disclosure);
    expect(screen.getByText("已有安排 4")).toBeVisible();
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

  it("blocks an edited event range whose end is not after its start", async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    render(<ApprovalCard proposal={proposal} onDecision={onDecision} />);

    await userEvent.click(screen.getByRole("button", { name: "调整后批准" }));
    fireEvent.change(screen.getByLabelText(/开始时间（Asia\/Shanghai）/), {
      target: { value: "2026-07-20T17:00" },
    });
    await userEvent.click(screen.getByRole("button", { name: "保存修改并批准" }));

    expect(screen.getByRole("alert")).toHaveTextContent("结束时间必须晚于开始时间");
    expect(onDecision).not.toHaveBeenCalled();
  });

  it("prefills partial legacy event edits and submits the refreshed version", async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    const updateProposal: ActionProposal = {
      ...proposal,
      action_type: "update_event",
      action_payload: {
        event_id: "44444444-4444-4444-8444-444444444444",
        expected_version: 2,
        title: null,
        start_at: null,
        end_at: null,
      },
      display_context: {
        allowed_decisions: ["approve", "edit", "reject"],
        current_version: 3,
        conflict_check: "completed",
        conflicts: [],
        review_complete: true,
        review_items: [{
          title: "现有评审",
          proposed_start_at: "2026-07-20T07:00:00Z",
          proposed_end_at: "2026-07-20T08:00:00Z",
        }],
      },
    };
    render(<ApprovalCard proposal={updateProposal} onDecision={onDecision} />);

    await userEvent.click(screen.getByRole("button", { name: "调整后批准" }));
    expect(screen.getByLabelText("日程标题")).toHaveValue("现有评审");
    expect(screen.getByLabelText(/开始时间（Asia\/Shanghai）/)).toHaveValue("2026-07-20T15:00");
    expect(screen.getByLabelText(/结束时间（Asia\/Shanghai）/)).toHaveValue("2026-07-20T16:00");
    await userEvent.click(screen.getByRole("button", { name: "保存修改并批准" }));

    expect(onDecision).toHaveBeenCalledWith("edit", expect.objectContaining({
      actionPayload: expect.objectContaining({
        event_id: "44444444-4444-4444-8444-444444444444",
        expected_version: 3,
        title: "现有评审",
        start_at: "2026-07-20T07:00:00Z",
        end_at: "2026-07-20T08:00:00Z",
      }),
    }));
  });

  it("keeps the editor open when the server needs more review information", async () => {
    const incompleteProposal: ActionProposal = {
      ...proposal,
      status: "awaiting_approval",
      display_context: {
        allowed_decisions: ["approve", "edit", "reject"],
        review_complete: false,
        review_items: [],
        conflicts: [],
      },
    };
    const onDecision = vi.fn().mockResolvedValue({
      proposal: incompleteProposal,
      resume_queued: false,
    });
    const completeProposal = {
      ...incompleteProposal,
      display_context: {
        ...incompleteProposal.display_context,
        review_complete: true,
        review_items: [{ title: "项目评审" }],
      },
    };
    const { rerender } = render(<ApprovalCard proposal={completeProposal} onDecision={onDecision} />);

    await userEvent.click(screen.getByRole("button", { name: "调整后批准" }));
    await userEvent.click(screen.getByRole("button", { name: "保存修改并批准" }));

    expect(screen.getByRole("alert")).toHaveTextContent("暂时无法完整核对这项修改");
    expect(screen.getByLabelText("日程标题")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存修改并批准" })).toBeInTheDocument();
    rerender(<ApprovalCard proposal={incompleteProposal} onDecision={onDecision} />);
    expect(screen.getByLabelText("日程标题")).toBeInTheDocument();
  });

  it("opens and focuses the editor while keeping mutation payloads free of display-only fields", async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    const mutationProposal: ActionProposal = {
      ...proposal,
      action_type: "mutate_events",
      action_payload: {
        operations: [{
          action: "update",
          event_id: "44444444-4444-4444-8444-444444444444",
          expected_version: 2,
          title: "论文讨论",
          time: { kind: "relative", offset: 1, unit: "day" },
        }],
      },
      display_context: {
        allowed_decisions: ["approve", "edit", "reject"],
        conflict_check: "completed",
        conflicts: [],
        review_complete: true,
        review_notice: "这项日程在提出审批后已有更新。已载入最新安排，请重新核对后再次确认。",
        review_items: [{ title: "论文讨论", detail: "调整日程时间" }],
        resolved_operations: [{
          action: "update",
          event_id: "44444444-4444-4444-8444-444444444444",
          expected_version: 3,
          current_version: 3,
          version_stale: true,
          title: "论文讨论",
          time: {
            kind: "absolute",
            start_at: "2026-07-20T07:00:00Z",
            end_at: "2026-07-20T08:00:00Z",
          },
          display_title: "论文讨论",
          existing_start_at: "2026-07-19T07:00:00Z",
          existing_end_at: "2026-07-19T08:00:00Z",
          display_task_title: "答辩准备",
        }],
      },
    };
    render(<ApprovalCard proposal={mutationProposal} onDecision={onDecision} />);

    const editButton = screen.getByRole("button", { name: "调整后批准" });
    expect(screen.getByRole("status")).toHaveTextContent("提出审批后已有更新");
    await userEvent.click(editButton);
    const details = screen.getByText("查看操作详情").closest("details");
    expect(details).toHaveAttribute("open");
    const title = screen.getByLabelText("日程标题");
    expect(title).toHaveFocus();
    await userEvent.click(screen.getByRole("button", { name: "取消编辑" }));
    expect(editButton).toHaveFocus();

    await userEvent.click(editButton);
    fireEvent.change(screen.getByLabelText("日程标题"), { target: { value: "新时间的论文讨论" } });
    await userEvent.click(screen.getByRole("button", { name: "保存修改并批准" }));

    expect(onDecision).toHaveBeenCalledWith("edit", expect.objectContaining({
      actionPayload: {
        operations: [{
          action: "update",
          event_id: "44444444-4444-4444-8444-444444444444",
          expected_version: 3,
          title: "新时间的论文讨论",
          time: {
            kind: "absolute",
            start_at: "2026-07-20T07:00:00Z",
            end_at: "2026-07-20T08:00:00Z",
          },
        }],
      },
    }));
  });

  it("shows existing times for a title-only mutation without adding a time change", async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    const titleOnlyProposal: ActionProposal = {
      ...proposal,
      action_type: "mutate_events",
      action_payload: {
        operations: [{
          action: "update",
          event_id: "44444444-4444-4444-8444-444444444444",
          expected_version: 3,
          title: "现有评审",
          time: null,
        }],
      },
      display_context: {
        allowed_decisions: ["approve", "edit", "reject"],
        conflict_check: "completed",
        conflicts: [],
        review_complete: true,
        review_items: [{ title: "现有评审", detail: "修改标题" }],
        resolved_operations: [{
          action: "update",
          event_id: "44444444-4444-4444-8444-444444444444",
          expected_version: 3,
          title: "现有评审",
          time: null,
          display_title: "现有评审",
          existing_start_at: "2026-07-20T07:00:00Z",
          existing_end_at: "2026-07-20T08:00:00Z",
        }],
      },
    };
    render(<ApprovalCard proposal={titleOnlyProposal} onDecision={onDecision} />);

    await userEvent.click(screen.getByRole("button", { name: "调整后批准" }));
    expect(screen.getByLabelText(/开始时间（Asia\/Shanghai）/)).toHaveValue("2026-07-20T15:00");
    expect(screen.getByLabelText(/结束时间（Asia\/Shanghai）/)).toHaveValue("2026-07-20T16:00");
    fireEvent.change(screen.getByLabelText("日程标题"), { target: { value: "新评审标题" } });
    await userEvent.click(screen.getByRole("button", { name: "保存修改并批准" }));

    expect(onDecision).toHaveBeenCalledWith("edit", expect.objectContaining({
      actionPayload: {
        operations: [{
          action: "update",
          event_id: "44444444-4444-4444-8444-444444444444",
          expected_version: 3,
          title: "新评审标题",
          time: null,
        }],
      },
    }));
  });

  it("preserves the other existing time when editing one side of a mutation", async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    const titleOnlyProposal: ActionProposal = {
      ...proposal,
      action_type: "mutate_events",
      action_payload: {
        operations: [{
          action: "update",
          event_id: "44444444-4444-4444-8444-444444444444",
          expected_version: 3,
          title: "现有评审",
          time: null,
        }],
      },
      display_context: {
        allowed_decisions: ["approve", "edit", "reject"],
        conflict_check: "completed",
        conflicts: [],
        review_complete: true,
        review_items: [{ title: "现有评审", detail: "调整时间" }],
        resolved_operations: [{
          action: "update",
          event_id: "44444444-4444-4444-8444-444444444444",
          expected_version: 3,
          title: "现有评审",
          time: null,
          display_title: "现有评审",
          existing_start_at: "2026-07-20T07:00:00Z",
          existing_end_at: "2026-07-20T08:00:00Z",
        }],
      },
    };
    render(<ApprovalCard proposal={titleOnlyProposal} onDecision={onDecision} />);

    await userEvent.click(screen.getByRole("button", { name: "调整后批准" }));
    fireEvent.change(screen.getByLabelText(/开始时间（Asia\/Shanghai）/), {
      target: { value: "2026-07-20T14:00" },
    });
    await userEvent.click(screen.getByRole("button", { name: "保存修改并批准" }));

    expect(onDecision).toHaveBeenCalledWith("edit", expect.objectContaining({
      actionPayload: {
        operations: [{
          action: "update",
          event_id: "44444444-4444-4444-8444-444444444444",
          expected_version: 3,
          title: "现有评审",
          time: {
            kind: "absolute",
            start_at: "2026-07-20T06:00:00.000Z",
            end_at: "2026-07-20T08:00:00Z",
          },
        }],
      },
    }));
  });

  it("blocks an ambiguous repeated local time while editing an approval", async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    render(<ApprovalCard proposal={proposal} timezone="America/New_York" onDecision={onDecision} />);

    await userEvent.click(screen.getByRole("button", { name: "调整后批准" }));
    await userEvent.click(screen.getByText("查看操作详情"));
    fireEvent.change(screen.getByLabelText(/开始时间（America\/New_York）/), {
      target: { value: "2026-11-01T01:30" },
    });

    expect(await screen.findByText(/这个时间在 America\/New_York 会出现两次/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "保存修改并批准" }));
    expect(onDecision).not.toHaveBeenCalled();
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
        review_complete: true,
        review_items: [{
          title: "项目评审",
          detail: "当前日程",
          time_label: "日程时间",
          start_at: "2026-07-20T07:00:00Z",
          end_at: "2026-07-20T08:00:00Z",
        }],
        object_name: "项目评审",
        impact_scope: "Cancels one existing calendar event",
      },
    };

    render(<ApprovalCard proposal={cancellation} onDecision={vi.fn()} />);

    expect(screen.getByText("取消日程")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认并应用" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "拒绝" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑后批准" })).not.toBeInTheDocument();
    expect(screen.queryByText(/冲突检查/)).not.toBeInTheDocument();
  });

  it("blocks approval when a high-risk action has an incomplete backend preview", () => {
    const incomplete: ActionProposal = {
      ...proposal,
      action_type: "set_reminder_target",
      action_payload: { reminder_id: "44444444-4444-4444-8444-444444444444" },
      display_context: {
        allowed_decisions: ["approve", "reject"],
        action_title: "更改提醒关联对象",
        action_summary: "将更改提醒关联的对象。",
        review_complete: false,
      },
    };

    render(<ApprovalCard proposal={incomplete} onDecision={vi.fn()} />);

    expect(screen.getByRole("status")).toHaveTextContent("暂时无法读取完整变化，因此不能确认这项操作");
    expect(screen.queryByRole("button", { name: "确认并应用" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "拒绝" })).toBeInTheDocument();
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

  it("uses the account timezone and never invents recurring occurrences", () => {
    const recurring: ActionProposal = {
      ...proposal,
      action_type: "create_recurring_event",
      action_payload: {
        title: "晨间阅读",
        time: { kind: "absolute", start_at: "2026-07-20T07:00:00Z", end_at: "2026-07-20T07:30:00Z" },
        frequency: "daily",
        occurrence_count: 3,
      },
      display_context: { allowed_decisions: ["approve", "reject"] },
    };

    render(<ApprovalCard proposal={recurring} timezone="Europe/London" onDecision={vi.fn()} />);

    expect(screen.getByText("2026/07/20 08:00")).toBeInTheDocument();
    expect(screen.getByText("共 3 次；详细日期暂不可用。")).toBeInTheDocument();
    expect(screen.queryByLabelText("周期日程实例预览")).not.toBeInTheDocument();
  });
});
