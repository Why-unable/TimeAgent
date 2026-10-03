import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { InteractionArtifact } from "../src/api/interactions";
import { ensureInteraction, submitInteraction } from "../src/api/interactions";
import { CompletionHarvest } from "../src/components/today/completion-check-in";

vi.mock("../src/api/interactions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/interactions")>();
  return {
    ...actual,
    ensureInteraction: vi.fn(),
    recordInteractionTelemetry: vi.fn(async () => undefined),
    submitInteraction: vi.fn(),
  };
});

vi.mock("../src/api/tasks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/tasks")>();
  return {
    ...actual,
    getTask: vi.fn(async () => ({
      id: "11111111-1111-4111-8111-111111111111",
      title: "写论文",
      estimated_minutes: 60,
      planned_start_at: "2026-07-20T09:00:00Z",
      planned_end_at: "2026-07-20T10:00:00Z",
    })),
    getTaskExecutionSummary: vi.fn(async () => ({
      active_seconds: 4500,
      planned_seconds: 3600,
      evidence_status: "measured",
    })),
  };
});

vi.mock("../src/api/time-memory", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/time-memory")>();
  return {
    ...actual,
    getDurationRecommendation: vi.fn(async () => ({
      task_id: "11111111-1111-4111-8111-111111111111",
      original_estimate_minutes: 60,
      recommended_minutes: 78,
      duration_multiplier: 1.3,
      segment: "writing",
      confidence: 0.8,
      sample_count: 5,
      source: "decision_profile",
      fallback_reason: null,
      evidence: [],
      classification: {},
      feature_version: "test",
      expires_at: "2026-07-21T00:00:00Z",
      decay_half_life_days: 30,
    })),
  };
});

const taskId = "11111111-1111-4111-8111-111111111111";

function completionInteraction(
  overrides: Partial<InteractionArtifact> = {},
): InteractionArtifact {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    conversation_id: null,
    agent_run_id: null,
    plan_id: null,
    plan_version: null,
    task_id: taskId,
    type: "task_completion",
    payload: {},
    allowed_actions: ["submit_feedback", "dismiss"],
    status: "pending",
    expires_at: "2026-07-21T00:00:00Z",
    version: 1,
    created_at: "2026-07-20T10:00:00Z",
    updated_at: "2026-07-20T10:00:00Z",
    resolved_at: null,
    ...overrides,
  } as InteractionArtifact;
}

function memoryInteraction(): InteractionArtifact {
  return completionInteraction({
    id: "33333333-3333-4333-8333-333333333333",
    type: "memory_suggestion",
    allowed_actions: ["accept", "dismiss"],
  });
}

function renderCheckIn(interaction: InteractionArtifact, onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CompletionHarvest interaction={interaction} onClose={onClose} />
    </QueryClientProvider>,
  );
  return onClose;
}

describe("CompletionHarvest", () => {
  beforeEach(() => {
    vi.mocked(ensureInteraction).mockReset();
    vi.mocked(submitInteraction).mockReset();
  });

  it("records optional structured feedback and updates Memory only after explicit consent", async () => {
    const original = completionInteraction();
    const feedbackSaved = completionInteraction({
      version: 2,
      payload: { completion_feedback: { rating: "longer", reason: "more_complex" } },
    });
    vi.mocked(submitInteraction)
      .mockResolvedValueOnce({
        accepted: true,
        detail: null,
        interaction: feedbackSaved,
        plan: null,
        reason_codes: [],
        conflicts: [],
        candidate: null,
        replayed: false,
      })
      .mockResolvedValueOnce({
        accepted: true,
        detail: null,
        interaction: memoryInteraction(),
        plan: null,
        reason_codes: [],
        conflicts: [],
        candidate: null,
        replayed: false,
      })
      .mockResolvedValueOnce({
        accepted: true,
        detail: null,
        interaction: { ...feedbackSaved, status: "abandoned" },
        plan: null,
        reason_codes: [],
        conflicts: [],
        candidate: null,
        replayed: false,
      });
    vi.mocked(ensureInteraction).mockResolvedValue(memoryInteraction());
    const onClose = renderCheckIn(original);

    expect(await screen.findByText("计划时长：60 分钟")).toBeInTheDocument();
    expect(screen.getByText("实际投入：75 分钟")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "比预计久" }));
    await userEvent.click(screen.getByRole("button", { name: "补充原因（可选）" }));
    await userEvent.selectOptions(screen.getByLabelText("补充原因（可选）"), "more_complex");
    await userEvent.click(screen.getByRole("button", { name: "记录反馈" }));

    expect(await screen.findByText(/最近 5 个类似任务样本/)).toBeInTheDocument();
    expect(vi.mocked(submitInteraction).mock.calls[0][1]).toMatchObject({
      action: "submit_feedback",
      values: { rating: "longer", reason: "more_complex" },
    });
    expect(vi.mocked(submitInteraction)).toHaveBeenCalledTimes(1);

    await userEvent.click(await screen.findByRole("button", { name: "更新偏好" }));
    await waitFor(() => expect(vi.mocked(submitInteraction)).toHaveBeenCalledTimes(3));
    expect(vi.mocked(submitInteraction).mock.calls[1][1]).toMatchObject({
      action: "accept",
      values: {},
    });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("keeps a saved feedback version when a parent rerenders with a stale interaction", async () => {
    const original = completionInteraction();
    const feedbackSaved = completionInteraction({
      version: 2,
      payload: { completion_feedback: { rating: "about_right" } },
    });
    vi.mocked(submitInteraction).mockResolvedValue({
      accepted: true,
      detail: null,
      interaction: feedbackSaved,
      plan: null,
      reason_codes: [],
      conflicts: [],
      candidate: null,
      replayed: false,
    });
    vi.mocked(ensureInteraction).mockRejectedValue(new Error("No memory suggestion in this test."));

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <CompletionHarvest interaction={original} onClose={vi.fn()} />
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "差不多" }));
    await userEvent.click(screen.getByRole("button", { name: "记录反馈" }));
    expect(await screen.findByText("已记录：差不多")).toBeInTheDocument();

    view.rerender(
      <QueryClientProvider client={client}>
        <CompletionHarvest
          interaction={{ ...original, updated_at: "2026-07-20T10:01:00Z" }}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("已记录：差不多")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "记录反馈" })).not.toBeInTheDocument();
  });

  it("allows the user to skip without filling feedback fields", async () => {
    const original = completionInteraction();
    const onClose = vi.fn();
    vi.mocked(submitInteraction).mockResolvedValue({
      accepted: true,
      detail: null,
      interaction: { ...original, status: "abandoned" },
      plan: null,
      reason_codes: [],
      conflicts: [],
      candidate: null,
      replayed: false,
    });
    renderCheckIn(original, onClose);

    await userEvent.click(await screen.findByRole("button", { name: "跳过" }));

    expect(vi.mocked(submitInteraction).mock.calls[0][1]).toMatchObject({
      action: "dismiss",
      values: {},
    });
    expect(onClose).toHaveBeenCalledOnce();
  });
});
