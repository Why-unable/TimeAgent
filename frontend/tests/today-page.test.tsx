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
};

function renderPage() {
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
  it("renders the backend summary without recomputing its business buckets", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(summary))));

    renderPage();

    expect(await screen.findByRole("heading", { name: "今天" })).toBeInTheDocument();
    expect(screen.getByText(/2026年7月20日/)).toBeInTheDocument();
    expect(screen.getAllByText("项目会议").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("计划写作").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("今日交付").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("补交周报").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("提交前提醒").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("1 小时后")).toBeInTheDocument();
    expect(screen.getByText("项目会议 与 计划写作")).toBeInTheDocument();
    expect(screen.getByText("Asia/Shanghai", { exact: false })).toBeInTheDocument();
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
  });

  it("shows an authenticated loading failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 403 })));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("无法读取今日工作台");
  });
});
