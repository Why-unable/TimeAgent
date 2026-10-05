import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { TodayPage } from "../src/pages/today-page";

const event = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "项目会议",
  description: "",
  start_at: "2026-07-20T05:00:00Z",
  end_at: "2026-07-20T06:00:00Z",
  timezone: "Asia/Shanghai",
  location: "会议室 A",
  status: "confirmed",
  visibility: "private",
  recurrence_rule: "",
  source: "local",
  external_id: "",
  created_by: 1,
  version: 1,
  created_at: "2026-07-19T01:00:00Z",
  updated_at: "2026-07-19T01:00:00Z",
};

const baseTask = {
  id: "21111111-1111-4111-8111-111111111111",
  project: "发布计划",
  parent_task: null,
  title: "计划写作",
  description: "",
  status: "pending",
  priority: "high",
  due_at: null,
  estimated_minutes: 60,
  planned_start_at: "2026-07-20T05:30:00Z",
  planned_end_at: "2026-07-20T06:30:00Z",
  actual_started_at: null,
  completed_at: null,
  source: "local",
  tags: [],
  created_at: "2026-07-19T01:00:00Z",
  updated_at: "2026-07-19T01:00:00Z",
};

const dueTask = {
  ...baseTask,
  id: "31111111-1111-4111-8111-111111111111",
  title: "今日交付",
  due_at: "2026-07-20T10:00:00Z",
  planned_start_at: null,
  planned_end_at: null,
};

const overdueTask = {
  ...dueTask,
  id: "41111111-1111-4111-8111-111111111111",
  title: "补交周报",
  due_at: "2026-07-19T10:00:00Z",
};

const summary = {
  date: "2026-07-20",
  timezone: "Asia/Shanghai",
  generated_at: "2026-07-20T04:00:00Z",
  day_start_at: "2026-07-19T16:00:00Z",
  day_end_at: "2026-07-20T16:00:00Z",
  events: [event],
  planned_tasks: [baseTask],
  due_tasks: [dueTask],
  overdue_tasks: [overdueTask],
  unfinished_tasks: [baseTask, dueTask, overdueTask],
  completed_tasks: [],
  pending_reminders: [
    {
      id: "51111111-1111-4111-8111-111111111111",
      target_type: "custom",
      target_id: null,
      title: "提交前提醒",
      trigger_at: "2026-07-20T09:00:00Z",
      timezone: "Asia/Shanghai",
      channel: "console",
      status: "pending",
      deduplication_key: "today-test",
      queued_at: null,
      sent_at: null,
      retry_count: 0,
      failure_reason: "",
      created_at: "2026-07-19T01:00:00Z",
      updated_at: "2026-07-19T01:00:00Z",
    },
  ],
  conflicts: [
    {
      first: {
        kind: "event",
        id: event.id,
        title: event.title,
        start_at: event.start_at,
        end_at: event.end_at,
      },
      second: {
        kind: "task",
        id: baseTask.id,
        title: baseTask.title,
        start_at: baseTask.planned_start_at,
        end_at: baseTask.planned_end_at,
      },
      overlap_start_at: "2026-07-20T05:30:00Z",
      overlap_end_at: "2026-07-20T06:00:00Z",
    },
  ],
  next_event: event,
  minutes_until_next_event: 60,
  execution_now: [],
  execution_next: [{
    kind: "event",
    id: event.id,
    title: event.title,
    start_at: event.start_at,
    end_at: event.end_at,
    status: null,
    due_at: null,
  }],
  execution_later: [
    { kind: "task", id: baseTask.id, title: baseTask.title, start_at: baseTask.planned_start_at, end_at: baseTask.planned_end_at, status: "pending", due_at: null },
    { kind: "task", id: overdueTask.id, title: overdueTask.title, start_at: null, end_at: null, status: "pending", due_at: overdueTask.due_at },
    { kind: "task", id: dueTask.id, title: dueTask.title, start_at: null, end_at: null, status: "pending", due_at: dueTask.due_at },
  ],
};

function renderPage() {
  const configuredFetch = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes("/api/v1/interactions/")) {
      return new Response("{}", { status: 503 });
    }
    return configuredFetch(input, init);
  }));
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <TodayPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TodayPage", () => {
  it("offers quick actions when the day is empty", async () => {
    const emptySummary = {
      ...summary,
      events: [],
      planned_tasks: [],
      due_tasks: [],
      overdue_tasks: [],
      unfinished_tasks: [],
      completed_tasks: [],
      pending_reminders: [],
      conflicts: [],
      next_event: null,
      minutes_until_next_event: null,
      execution_now: [],
      execution_next: [],
      execution_later: [],
    };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(emptySummary))));

    renderPage();

    expect(await screen.findByRole("heading", { name: "暂时没有正在进行的安排" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "让助理安排今天" })).toHaveAttribute("href", "/chat?auto_send=1&prompt=%E5%B8%AE%E6%88%91%E5%AE%89%E6%8E%92%E4%BB%8A%E5%A4%A9%E7%9A%84%E4%BB%BB%E5%8A%A1");
  });

  it("renders the backend summary without recomputing its business buckets", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(summary))));

    renderPage();

    expect(await screen.findByRole("heading", { name: "今天" })).toBeInTheDocument();
    expect(screen.getByText(/2026年7月20日/)).toBeInTheDocument();
    expect(screen.getAllByText("项目会议").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("计划写作")).toHaveLength(2); // responsive mobile and desktop surfaces
    expect(screen.getAllByText("今日交付").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("补交周报").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("提交前提醒").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("1 小时后")).toBeInTheDocument();
    expect(screen.getByText("项目会议 与 计划写作")).toBeInTheDocument();
    expect(screen.getByText("Asia/Shanghai", { exact: false })).toBeInTheDocument();
    expect(screen.getAllByRole("region", { name: "今日执行面板" })).toHaveLength(1);
    expect(screen.getByTestId("today-focus")).toHaveTextContent("项目会议");
    expect(screen.getAllByRole("link", { name: "查看日程" })[0]).toHaveAttribute("href", "/calendar");
    const eventChatLink = screen.getAllByRole("link", { name: "调整安排" })[0];
    expect(eventChatLink).toHaveAttribute("href", expect.stringContaining("auto_send=1"));
    expect(new URL(eventChatLink.getAttribute("href") as string, "http://localhost").searchParams.get("prompt"))
      .toContain(`event_id=${event.id}`);
  });

  it("renders insight evidence as local time without exposing a raw timestamp or nested surface", async () => {
    const rawDueAt = "2026-07-19T10:00:00+00:00";
    const insight = {
      id: "61111111-1111-4111-8111-111111111111",
      kind: "task_overdue",
      severity: "warning",
      status: "open",
      title: "任务已逾期",
      summary: "请检查这项任务的后续安排。",
      evidence: { due_at: rawDueAt },
      deduplication_key: "overdue-test",
      detected_at: "2026-07-20T04:00:00Z",
      expires_at: "2026-07-21T04:00:00Z",
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      return new Response(JSON.stringify(url.includes("/insights/") ? [insight] : summary));
    }));

    renderPage();

    const alertSection = await screen.findByRole("region", { name: "需要留意" });
    expect(alertSection).toHaveTextContent("截止：");
    expect(alertSection).toHaveTextContent("18:00");
    expect(alertSection).not.toHaveTextContent(rawDueAt);
    expect(alertSection.querySelector("[data-surface] [data-surface]")).toBeNull();
  });

  it("offers start, complete, and adjust actions for the next task", async () => {
    let signalUrl = "";
    const taskSummary = {
      ...summary,
      events: [],
      planned_tasks: [baseTask],
      due_tasks: [],
      overdue_tasks: [],
      pending_reminders: [],
      conflicts: [],
      next_event: null,
      minutes_until_next_event: null,
      execution_now: [],
      execution_next: [{
        kind: "task",
        id: baseTask.id,
        title: baseTask.title,
        start_at: baseTask.planned_start_at,
        end_at: baseTask.planned_end_at,
        status: "pending",
        due_at: null,
      }],
      execution_later: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (init?.method === "POST") {
          signalUrl = url;
          return new Response(JSON.stringify({ task: baseTask, signal_type: "started" }));
        }
        return new Response(JSON.stringify(taskSummary));
      }),
    );

    renderPage();

    expect(await screen.findAllByRole("region", { name: "今日执行面板" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: `开始任务：${baseTask.title}` })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: `完成任务：${baseTask.title}` })).toHaveLength(2); // mobile and desktop only
    expect(screen.getAllByRole("link", { name: `查看任务：${baseTask.title}` })[0]).toHaveAttribute("href", "/tasks");
    const taskChatLink = screen.getAllByRole("link", { name: `让助理协助调整任务：${baseTask.title}` })[0];
    expect(new URL(taskChatLink.getAttribute("href") as string, "http://localhost").searchParams.get("prompt"))
      .toContain(`task_id=${baseTask.id}`);

    await userEvent.click(screen.getAllByRole("button", { name: `开始任务：${baseTask.title}` })[0]);
    await waitFor(() => expect(signalUrl).toContain(`/tasks/${baseTask.id}/execution-signals/`));
  });

  it("completes a task and refreshes the Today summary", async () => {
    let completeUrl = "";
    let summaryReads = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (init?.method === "POST") {
          completeUrl = url;
          return new Response(JSON.stringify({ ...dueTask, status: "completed" }));
        }
        summaryReads += 1;
        return new Response(JSON.stringify(summary));
      }),
    );
    renderPage();

    const completeButtons = await screen.findAllByRole("button", { name: "完成任务：今日交付" });
    await userEvent.click(completeButtons[0]);

    await waitFor(() => {
      expect(completeUrl).toContain(`/tasks/${dueTask.id}/complete/`);
      expect(summaryReads).toBeGreaterThanOrEqual(2);
    });
    expect(await screen.findByText("今日交付：已完成")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "任务完成反馈" })).not.toBeInTheDocument();
  });

  it("opens optional completion feedback only after the user asks for it", async () => {
    const interaction = {
      id: "71111111-1111-4111-8111-111111111111",
      conversation_id: null,
      agent_run_id: null,
      plan_id: null,
      plan_version: null,
      task_id: dueTask.id,
      type: "task_completion",
      payload: {},
      allowed_actions: ["submit_feedback", "dismiss"],
      status: "pending",
      expires_at: "2026-07-21T00:00:00Z",
      version: 1,
      created_at: "2026-07-20T10:00:00Z",
      updated_at: "2026-07-20T10:00:00Z",
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/v1/today/")) return new Response(JSON.stringify(summary));
      if (url.includes("/api/v1/insights/")) return new Response("[]");
      if (url.includes("/api/v1/interactions/")) {
        if ((init?.method ?? "GET") === "POST" && url.endsWith("/interactions/")) {
          return new Response(JSON.stringify(interaction));
        }
        return new Response("[]");
      }
      if (url.endsWith(`/tasks/${dueTask.id}/complete/`)) {
        return new Response(JSON.stringify({ ...dueTask, status: "completed" }));
      }
      if (url.endsWith(`/tasks/${dueTask.id}/execution-summary/`)) {
        return new Response(JSON.stringify({
          task_id: dueTask.id,
          signal_count: 1,
          active_seconds: 0,
          planned_seconds: null,
          estimated_seconds: 1800,
          variance_vs_plan_seconds: null,
          variance_vs_estimate_seconds: null,
          evidence_status: "no_execution_evidence",
          open_started_at: null,
          last_signal_type: null,
        }));
      }
      if (url.endsWith(`/tasks/${dueTask.id}/`)) return new Response(JSON.stringify(dueTask));
      return new Response("[]");
    }));
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <TodayPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await userEvent.click((await screen.findAllByRole("button", { name: "完成任务：今日交付" }))[0]);
    expect(await screen.findByText("今日交付：已完成")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: "记录反馈" }));
    expect(await screen.findByRole("dialog", { name: "任务完成反馈" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "任务完成反馈" })).toBeInTheDocument();
  });

  it("shows an authenticated loading failure", async () => {
    let attempts = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      attempts += 1;
      return attempts === 1
        ? new Response("{}", { status: 403 })
        : new Response(JSON.stringify(summary));
    }));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("无法读取今天的安排");
    await userEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByTestId("today-focus")).toHaveTextContent("项目会议");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("records explicit false-positive feedback without silently disabling the kind", async () => {
    let actionBody: Record<string, unknown> | undefined;
    const insight = {
      id: "61111111-1111-4111-8111-111111111111",
      kind: "deadline_risk",
      severity: "medium",
      status: "open",
      title: "截止风险",
      summary: "任务可能无法按时完成。",
      evidence: { due_at: "2026-07-20T10:00:00Z" },
      deduplication_key: "deadline:e2e",
      detected_at: "2026-07-20T04:00:00Z",
      expires_at: "2026-07-21T04:00:00Z",
      snoozed_until: null,
      acted_at: null,
      attention_decision: "NORMAL_NOTIFICATION",
      attention_reason: "within_policy",
      attention_decided_at: "2026-07-20T04:00:00Z",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes(`/insights/${insight.id}/action/`)) {
          actionBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
          return new Response(JSON.stringify({ ...insight, status: "false_positive" }));
        }
        if (url.endsWith("/api/v1/insights/")) {
          return new Response(JSON.stringify([insight]));
        }
        return new Response(JSON.stringify(summary));
      }),
    );
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /标记为不准确：/ }));
    await waitFor(() => expect(actionBody).toEqual({
      action: "false_positive",
      disable_kind: false,
    }));
  });
});
