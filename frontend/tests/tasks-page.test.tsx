import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { TasksPage } from "../src/pages/tasks-page";

const preference = { timezone: "Asia/Shanghai", locale: "zh-CN" };
const pendingTask = {
  id: "21111111-1111-4111-8111-111111111111",
  project: "发布计划",
  parent_task: null,
  title: "准备发布报告",
  description: "整理本周指标",
  status: "pending",
  priority: "high",
  due_at: "2026-07-20T10:00:00Z",
  estimated_minutes: 60,
  planned_start_at: null,
  planned_end_at: null,
  actual_started_at: null,
  completed_at: null,
  source: "local",
  tags: ["工作", "报告"],
  created_at: "2026-07-18T01:00:00Z",
  updated_at: "2026-07-18T01:00:00Z",
};
const completedTask = {
  ...pendingTask,
  id: "31111111-1111-4111-8111-111111111111",
  title: "归档旧报告",
  status: "completed",
  completed_at: "2026-07-18T02:00:00Z",
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <TasksPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TasksPage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-07-20T04:00:00Z"));
  });

  afterEach(() => vi.useRealTimers());

  it("filters tasks and distinguishes due time from planned time", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const body = String(input).includes("preferences")
          ? preference
          : [pendingTask, completedTask];
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
    renderPage();

    expect(await screen.findByText("准备发布报告")).toBeInTheDocument();
    expect(screen.getByText("截止时间")).toBeInTheDocument();
    expect(screen.getByText("计划执行时间")).toBeInTheDocument();
    expect(screen.queryByText("归档旧报告")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "已完成" }));
    expect(await screen.findByText("归档旧报告")).toBeInTheDocument();
    expect(screen.queryByText("准备发布报告")).not.toBeInTheDocument();
  });

  it("creates a task with separate due and planned timestamps", async () => {
    let createBody: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("preferences")) return new Response(JSON.stringify(preference));
        if (init?.method === "POST") {
          createBody = JSON.parse(String(init.body)) as Record<string, unknown>;
          return new Response(JSON.stringify(pendingTask), { status: 201 });
        }
        return new Response(JSON.stringify([]));
      }),
    );
    renderPage();
    await screen.findByText("当前分类暂无任务");

    await userEvent.click(screen.getByRole("button", { name: "新建任务" }));
    await userEvent.type(screen.getByLabelText("任务标题"), "编写上线清单");
    fireEvent.change(screen.getByLabelText(/截止时间 due_at/), {
      target: { value: "2026-07-21T18:00" },
    });
    fireEvent.change(screen.getByLabelText(/计划开始/), {
      target: { value: "2026-07-21T09:00" },
    });
    fireEvent.change(screen.getByLabelText(/计划结束/), {
      target: { value: "2026-07-21T10:00" },
    });
    await userEvent.type(screen.getByLabelText(/标签/), "工作, 发布");
    await userEvent.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() => expect(createBody).toBeDefined());
    expect(createBody).toMatchObject({
      title: "编写上线清单",
      due_at: "2026-07-21T10:00:00.000Z",
      planned_start_at: "2026-07-21T01:00:00.000Z",
      planned_end_at: "2026-07-21T02:00:00.000Z",
      tags: ["工作", "发布"],
    });
  });

  it("completes a pending task through the dedicated endpoint", async () => {
    let completeUrl = "";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("preferences")) return new Response(JSON.stringify(preference));
        if (init?.method === "POST") {
          completeUrl = url;
          return new Response(JSON.stringify({ ...pendingTask, status: "completed" }));
        }
        return new Response(JSON.stringify([pendingTask]));
      }),
    );
    renderPage();

    await userEvent.click(
      await screen.findByRole("button", { name: "完成任务：准备发布报告" }),
    );

    await waitFor(() => expect(completeUrl).toContain(`/tasks/${pendingTask.id}/complete/`));
  });

  it("records an explicit start signal for a pending task", async () => {
    let signalUrl = "";
    let signalBody: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("preferences")) return new Response(JSON.stringify(preference));
        if (init?.method === "POST") {
          signalUrl = url;
          signalBody = JSON.parse(String(init.body)) as Record<string, unknown>;
          return new Response(JSON.stringify({
            id: "signal-1",
            task: pendingTask.id,
            signal_type: "started",
            occurred_at: "2026-07-20T04:00:00Z",
            idempotency_key: "web-start-1",
            source: "web",
            metadata: {},
            created_at: "2026-07-20T04:00:00Z",
          }));
        }
        return new Response(JSON.stringify([pendingTask]));
      }),
    );
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "开始任务：准备发布报告" }));

    await waitFor(() => expect(signalUrl).toContain(`/tasks/${pendingTask.id}/execution-signals/`));
    expect(signalBody).toMatchObject({ signal_type: "started", source: "web" });
    expect(signalBody?.idempotency_key).toEqual(expect.any(String));
  });

  it("shows a task-level duration recommendation and records segment feedback", async () => {
    let feedbackBody: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("preferences")) return new Response(JSON.stringify(preference));
        if (url.includes("duration-recommendations")) {
          return new Response(JSON.stringify({
            task_id: pendingTask.id,
            original_estimate_minutes: 60,
            recommended_minutes: 75,
            duration_multiplier: 1.25,
            segment: "project:发布计划",
            confidence: 0.6,
            sample_count: 6,
            source: "explicit_segment_execution_calibration",
            fallback_reason: null,
            evidence: ["同项目 6 个完成任务"],
            classification: {
              category: "writing",
              confidence: 0.65,
              source: "deterministic-task-taxonomy-v1",
              matched_signals: ["报告"],
            },
            feature_version: "duration-recommendation-v2",
            expires_at: "2026-08-31T01:00:00Z",
            decay_half_life_days: 60,
          }));
        }
        if (url.endsWith("/api/v1/time-memory/me/decision-profile/") && init?.method === "POST") {
          feedbackBody = JSON.parse(String(init.body)) as Record<string, unknown>;
          return new Response(JSON.stringify({ id: "feedback-1" }), { status: 201 });
        }
        return new Response(JSON.stringify([pendingTask]));
      }),
    );
    renderPage();

    await userEvent.click(
      await screen.findByRole("button", { name: "查看估时建议：准备发布报告" }),
    );
    expect(await screen.findByText("建议预留 75 分钟")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "太短" }));
    await waitFor(() => expect(feedbackBody).toMatchObject({
      category: "duration_estimate",
      action: "too_short",
      value: {
        task_id: pendingTask.id,
        segment: "project:发布计划",
        recommended_minutes: 75,
      },
      source: "web",
    }));
  });
});
