import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { InteractionArtifact } from "../src/api/interactions";
import { recordInteractionTelemetry, submitInteraction } from "../src/api/interactions";
import type { SchedulePlan } from "../src/api/planning";
import { InteractivePlanTimeline, PriorityRanker } from "../src/components/planning/interactive-plan-timeline";

vi.mock("../src/api/interactions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/interactions")>();
  return {
    ...actual,
    recordInteractionTelemetry: vi.fn(async () => undefined),
    submitInteraction: vi.fn(),
  };
});

const firstTaskId = "11111111-1111-4111-8111-111111111111";
const secondTaskId = "22222222-2222-4222-8222-222222222222";
const planId = "33333333-3333-4333-8333-333333333333";

function makePlan(version = 1, items?: unknown[]): SchedulePlan {
  return {
    id: planId,
    strategy: "plan_tasks_only",
    items: items ?? [
      { task_id: firstTaskId, task_title: "论文", state: "placed", start_at: "2026-07-20T09:00:00Z", end_at: "2026-07-20T10:00:00Z", locked: false },
      { task_id: secondTaskId, task_title: "Redis", state: "placed", start_at: "2026-07-20T10:00:00Z", end_at: "2026-07-20T11:00:00Z", locked: false },
    ],
    constraints_snapshot: { timezone: "UTC" },
    decision_profile_snapshot: {},
    status: "draft",
    version,
    created_at: "2026-07-20T08:00:00Z",
    updated_at: "2026-07-20T08:00:00Z",
    expires_at: "2026-07-20T18:00:00Z",
    applied_at: null,
    abandoned_at: null,
    invalidated_at: null,
    invalidation_reason: "",
  } as SchedulePlan;
}

function makeInteraction(type: "priority_ranking" | "plan_timeline_edit"): InteractionArtifact {
  return {
    id: "44444444-4444-4444-8444-444444444444",
    conversation_id: null,
    agent_run_id: null,
    plan_id: planId,
    plan_version: 1,
    task_id: null,
    type,
    payload: { plan_id: planId },
    allowed_actions: type === "priority_ranking" ? ["reorder", "dismiss"] : ["edit", "dismiss"],
    status: "pending",
    expires_at: "2026-07-20T18:00:00Z",
    version: 1,
    created_at: "2026-07-20T08:00:00Z",
    updated_at: "2026-07-20T08:00:00Z",
    resolved_at: null,
  } as InteractionArtifact;
}

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const titles = new Map([[firstTaskId, "论文"], [secondTaskId, "Redis"]]);

describe("interactive planning controls", () => {
  beforeEach(() => {
    vi.mocked(submitInteraction).mockReset();
    vi.mocked(recordInteractionTelemetry).mockClear();
  });

  it("reorders tasks with keyboard buttons and sends a plan-local decision", async () => {
    const plan = makePlan();
    const updated = makePlan(2, [
      { task_id: secondTaskId, task_title: "Redis", state: "placed", planning_order: 0, start_at: "2026-07-20T10:00:00Z", end_at: "2026-07-20T11:00:00Z" },
      { task_id: firstTaskId, task_title: "论文", state: "placed", planning_order: 1, start_at: "2026-07-20T09:00:00Z", end_at: "2026-07-20T10:00:00Z" },
    ]);
    vi.mocked(submitInteraction).mockResolvedValue({
      accepted: true,
      detail: null,
      interaction: { ...makeInteraction("priority_ranking"), version: 2, plan_version: 2 },
      plan: updated,
      reason_codes: [],
      conflicts: [],
      candidate: null,
      replayed: false,
    });
    const onPlanChange = vi.fn();

    renderWithQuery(
      <PriorityRanker
        plan={plan}
        interaction={makeInteraction("priority_ranking")}
        taskTitles={titles}
        timezone="UTC"
        onPlanChange={onPlanChange}
        onSnooze={vi.fn()}
        onRefreshPlan={async () => undefined}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "下移：论文" }));
    await waitFor(() => expect(submitInteraction).toHaveBeenCalledOnce());
    const submitted = vi.mocked(submitInteraction).mock.calls[0][1];
    expect(submitted).toMatchObject({
      action: "reorder",
      values: { ordered_task_ids: [secondTaskId, firstTaskId] },
    });
    expect(onPlanChange).toHaveBeenCalledWith(updated);
    expect(screen.getAllByText(/永久优先级没有更改/).length).toBeGreaterThan(0);
  });

  it("supports keyboard time adjustment and resizes through the plan edit API", async () => {
    const plan = makePlan();
    const updated = makePlan(2, [
      { task_id: firstTaskId, task_title: "论文", state: "placed", start_at: "2026-07-20T09:15:00Z", end_at: "2026-07-20T10:45:00Z", planned_duration_minutes: 90 },
      { task_id: secondTaskId, task_title: "Redis", state: "placed", start_at: "2026-07-20T10:00:00Z", end_at: "2026-07-20T11:00:00Z" },
    ]);
    vi.mocked(submitInteraction).mockResolvedValue({
      accepted: true,
      detail: null,
      interaction: { ...makeInteraction("plan_timeline_edit"), version: 2, plan_version: 2 },
      plan: updated,
      reason_codes: [],
      conflicts: [],
      candidate: null,
      replayed: false,
    });

    renderWithQuery(
      <InteractivePlanTimeline
        plan={plan}
        interaction={makeInteraction("plan_timeline_edit")}
        taskTitles={titles}
        timezone="UTC"
        onPlanChange={vi.fn()}
        onSnooze={vi.fn()}
        onRefreshPlan={async () => undefined}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "推后 15 分钟：论文" }));
    const duration = screen.getAllByRole("spinbutton", { name: "时长（分钟）" })[0];
    fireEvent.change(duration, { target: { value: "90" } });
    await userEvent.click(screen.getAllByRole("button", { name: "保存" })[0]);
    await waitFor(() => expect(submitInteraction).toHaveBeenCalledOnce());

    const submitted = vi.mocked(submitInteraction).mock.calls[0][1];
    expect(submitted).toMatchObject({
      action: "edit",
      values: {
        items: [{
          task_id: firstTaskId,
          start_at: "2026-07-20T09:15:00.000Z",
          end_at: "2026-07-20T10:45:00.000Z",
        }],
      },
    });
  });

  it("rolls back rejected edits, explains backend conflicts, and accepts the suggested slot", async () => {
    const plan = makePlan();
    const interaction = makeInteraction("plan_timeline_edit");
    vi.mocked(submitInteraction)
      .mockResolvedValueOnce({
        accepted: false,
        detail: "Edited plan is invalid: schedule_conflict",
        interaction,
        plan,
        reason_codes: ["schedule_conflict"],
        conflicts: [{ kind: "event", label: "会议", start_at: "2026-07-20T09:15:00Z", end_at: "2026-07-20T10:00:00Z" }],
        candidate: { start_at: "2026-07-20T11:00:00Z", end_at: "2026-07-20T12:00:00Z" },
        replayed: false,
      })
      .mockResolvedValueOnce({
        accepted: true,
        detail: null,
        interaction: { ...interaction, version: 2, plan_version: 2 },
        plan: makePlan(2),
        reason_codes: [],
        conflicts: [],
        candidate: null,
        replayed: false,
      });
    const onPlanChange = vi.fn();

    renderWithQuery(
      <InteractivePlanTimeline
        plan={plan}
        interaction={interaction}
        taskTitles={titles}
        timezone="UTC"
        onPlanChange={onPlanChange}
        onSnooze={vi.fn()}
        onRefreshPlan={async () => undefined}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "推后 15 分钟：论文" }));
    await userEvent.click(screen.getAllByRole("button", { name: "保存" })[0]);
    expect(await screen.findByRole("alert")).toHaveTextContent("与现有日程或任务时间冲突");
    expect(await screen.findByRole("button", { name: /使用推荐时间/ })).toBeInTheDocument();
    expect(onPlanChange).toHaveBeenCalledWith(plan);

    await userEvent.click(screen.getByRole("button", { name: /使用推荐时间/ }));
    await waitFor(() => expect(submitInteraction).toHaveBeenCalledTimes(2));
    expect(vi.mocked(submitInteraction).mock.calls[1][1]).toMatchObject({
      values: {
        items: [{
          task_id: firstTaskId,
          start_at: "2026-07-20T11:00:00Z",
          end_at: "2026-07-20T12:00:00Z",
        }],
      },
    });
  });
});
