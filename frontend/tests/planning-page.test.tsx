import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";

import { PlanningPage } from "../src/pages/planning-page";

const task = {
  id: "21111111-1111-4111-8111-111111111111",
  project: "",
  parent_task: null,
  title: "准备发布报告",
  description: "",
  status: "pending",
  priority: "high",
  due_at: "2026-07-22T10:00:00Z",
  estimated_minutes: 60,
  planned_start_at: null,
  planned_end_at: null,
  actual_started_at: null,
  completed_at: null,
  source: "local",
  tags: [],
  version: 1,
  created_at: "2026-07-18T01:00:00Z",
  updated_at: "2026-07-18T01:00:00Z",
};

function renderPage(initialEntry = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <QueryClientProvider client={client}>
        <LocationProbe />
        <PlanningPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="current-location">{location.pathname}{location.search}</output>;
}

describe("PlanningPage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-07-20T01:00:00Z"));
  });

  afterEach(() => vi.useRealTimers());

  it("supports keyboard navigation and relationships in the planning mode tabs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const payload = url.includes("/capacity-forecast/")
          ? {
              total_schedulable_capacity_minutes: 0,
              remaining_free_minutes: 0,
              committed_minutes: 0,
              unplanned_minutes: 0,
              risk: "within_capacity",
              reason_codes: [],
            }
          : [];
        return new Response(JSON.stringify(payload), { status: 200 });
      }),
    );
    renderPage();

    const planTab = await screen.findByRole("tab", { name: "计划草案" });
    await userEvent.click(planTab);
    await userEvent.keyboard("{ArrowRight}");

    const replanTab = screen.getByRole("tab", { name: "局部调整" });
    expect(replanTab).toHaveFocus();
    expect(replanTab).toHaveAttribute("aria-selected", "true");
    expect(replanTab).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", replanTab.id);
  });

  it("reloads the linked plan when opened from an application failure", async () => {
    const planId = "41111111-1111-4111-8111-111111111111";
    const plan = {
      id: planId,
      strategy: "plan_tasks_only",
      status: "draft",
      version: 2,
      created_at: "2026-07-20T01:00:00Z",
      updated_at: "2026-07-20T01:05:00Z",
      expires_at: "2026-07-20T02:00:00Z",
      items: [{
        task_id: task.id,
        task_version: 1,
        state: "placed",
        start_at: "2026-07-20T02:00:00Z",
        end_at: "2026-07-20T03:00:00Z",
        locked: false,
        reason_codes: [],
      }],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith(`/api/v1/planning/plans/${planId}/`)) {
        return new Response(JSON.stringify(plan), { status: 200 });
      }
      if (url.includes("/capacity-forecast/")) {
        return new Response(JSON.stringify({
          total_schedulable_capacity_minutes: 0,
          remaining_free_minutes: 0,
          committed_minutes: 0,
          unplanned_minutes: 0,
          risk: "within_capacity",
          reason_codes: [],
        }), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage(`/planning?plan_id=${planId}`);

    expect(await screen.findByText("已载入最新计划，请核对当前状态和安排。")).toHaveAttribute("role", "status");
    expect(await screen.findByText("计划草稿 · 尚未应用到日程")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(`/api/v1/planning/plans/${planId}/`),
      expect.anything(),
    );
  });

  it("generates an explainable draft and routes application through HITL approval", async () => {
    let createBody: Record<string, unknown> | undefined;
    let editBody: Record<string, unknown> | undefined;
    const draft = (version: number, locked: boolean) => ({
      id: "41111111-1111-4111-8111-111111111111",
      strategy: "plan_tasks_only",
      constraints_snapshot: { snapshot_version: "planning-constraints-v1" },
      decision_profile_snapshot: { status: "unavailable" },
      status: "draft",
      version,
      created_at: "2026-07-20T01:00:00Z",
      updated_at: "2026-07-20T01:00:00Z",
      expires_at: "2026-07-20T02:00:00Z",
      applied_at: null,
      abandoned_at: null,
      invalidated_at: null,
      invalidation_reason: "",
      items: [{
        task_id: task.id,
        task_version: 1,
        state: "placed",
        start_at: "2026-07-20T02:00:00Z",
        end_at: "2026-07-20T03:00:00Z",
        locked,
        reason_codes: [],
      }],
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/v1/tasks/")) {
          return new Response(JSON.stringify([task]), { status: 200 });
        }
        if (url.endsWith("/api/v1/planning/automation-policies/")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.includes("/api/v1/time-memory/me/capacity-forecast/")) {
          return new Response(JSON.stringify({
            range_start: "2026-07-20T01:00:00Z",
            range_end: "2026-07-27T01:00:00Z",
            available_minutes: 480,
            committed_minutes: 120,
            unplanned_minutes: 600,
            risk: "over_capacity",
            reason_codes: ["unplanned_exceeds_free_capacity"],
          }), { status: 200 });
        }
        if (url.endsWith("/api/v1/planning/plans/") && init?.method === "POST") {
          createBody = JSON.parse(String(init.body)) as Record<string, unknown>;
          return new Response(JSON.stringify(draft(1, false)), { status: 201 });
        }
        if (url.includes("/edit/") && init?.method === "POST") {
          editBody = JSON.parse(String(init.body)) as Record<string, unknown>;
          return new Response(JSON.stringify(draft(2, true)), { status: 200 });
        }
        if (url.includes("/validate/") && init?.method === "POST") {
          return new Response(JSON.stringify({
            plan: draft(2, true),
            valid: true,
            reason_codes: [],
            checked_at: "2026-07-20T01:02:00Z",
          }), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }),
    );
    renderPage();

    expect(await screen.findByText("容量超载")).toBeInTheDocument();
    expect(screen.getByText("当前范围内可能有任务无法安排，请查看计划结果。")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "高级规划设置" }));
    await waitFor(() => expect(screen.getByRole("checkbox", { name: /准备发布报告/ })).toBeChecked());
    await userEvent.click(screen.getByRole("button", { name: "生成草案" }));

    expect(await screen.findByText("已安排")).toBeInTheDocument();
    expect(createBody).toMatchObject({ task_ids: [task.id], strategy: "plan_tasks_only" });
    expect(screen.getByRole("region", { name: "计划时间线" })).toBeInTheDocument();
    await userEvent.click(screen.getByText("高级调整（锁定或重新安排任务）"));
    await userEvent.click(screen.getByRole("button", { name: "锁定计划块：准备发布报告" }));
    await waitFor(() => expect(editBody).toMatchObject({
      expected_version: 1,
      items: [{ task_id: task.id, locked: true }],
    }));
    expect(await screen.findByRole("button", { name: "解锁计划块：准备发布报告" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "提交应用审批" }));
    await waitFor(() => expect(screen.getByTestId("current-location").textContent).toContain("/chat?"));
    const location = new URL(screen.getByTestId("current-location").textContent ?? "", "http://localhost");
    expect(location.pathname).toBe("/chat");
    expect(location.searchParams.get("auto_send")).toBe("1");
    expect(location.searchParams.get("prompt")).toContain("41111111-1111-4111-8111-111111111111");
    expect(location.searchParams.get("prompt")).toContain("版本：2");
  });

  it("compares deterministic alternatives and regenerates only selected items", async () => {
    let regenerateBody: Record<string, unknown> | undefined;
    const alternative = (id: string, ordering: string) => ({
      id,
      strategy: "plan_tasks_only",
      status: "draft",
      version: 1,
      created_at: "2026-07-20T01:00:00Z",
      updated_at: "2026-07-20T01:00:00Z",
      expires_at: "2026-07-20T02:00:00Z",
      applied_at: null,
      items: [
        {
          task_id: task.id,
          task_version: 1,
          state: "placed",
          start_at: "2026-07-20T02:00:00Z",
          end_at: "2026-07-20T03:00:00Z",
          locked: false,
          reason_codes: [],
        },
        { kind: "plan_evidence", evidence: { ordering } },
      ],
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/v1/tasks/")) {
          return new Response(JSON.stringify([task]), { status: 200 });
        }
        if (url.endsWith("/api/v1/planning/automation-policies/")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.includes("/api/v1/time-memory/me/capacity-forecast/")) {
          return new Response(JSON.stringify({
            range_start: "2026-07-20T01:00:00Z",
            range_end: "2026-07-27T01:00:00Z",
            available_minutes: 480,
            committed_minutes: 120,
            unplanned_minutes: 60,
            risk: "within_capacity",
            reason_codes: [],
          }), { status: 200 });
        }
        if (url.endsWith("/api/v1/planning/plans/compare/")) {
          return new Response(JSON.stringify({
            alternatives: [
              alternative("41111111-1111-4111-8111-111111111111", "priority_deadline"),
              alternative("42222222-2222-4222-8222-222222222222", "longest_first"),
            ],
            comparison: [
              { ordering: "priority_deadline", placed_count: 1, unplaced_count: 0 },
              { ordering: "longest_first", placed_count: 1, unplaced_count: 0 },
            ],
            claim: "deterministic_alternatives_not_global_optimum",
          }), { status: 201 });
        }
        if (url.includes("/regenerate/") && init?.method === "POST") {
          regenerateBody = JSON.parse(String(init.body)) as Record<string, unknown>;
          return new Response(JSON.stringify({
            ...alternative("41111111-1111-4111-8111-111111111111", "priority_deadline"),
            version: 2,
          }), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }),
    );
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "高级规划设置" }));
    await userEvent.click(screen.getByRole("button", { name: "比较两种方案" }));
    expect(await screen.findByRole("button", { name: /长任务优先/ })).toBeInTheDocument();
    await userEvent.click(screen.getByText("高级调整（锁定或重新安排任务）"));
    const checkboxes = screen.getAllByRole("checkbox", { name: /准备发布报告/ });
    await userEvent.click(checkboxes[1]);
    await userEvent.click(screen.getByRole("button", { name: "只重生成选中项" }));
    await waitFor(() => expect(regenerateBody).toMatchObject({
      expected_version: 1,
      task_ids: [task.id],
      ordering: "priority_deadline",
    }));
  });

  it("explains a skipped local time and blocks plan generation", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("preferences")) {
        return new Response(JSON.stringify({ timezone: "America/New_York", locale: "en-US" }));
      }
      if (url.endsWith("/api/v1/tasks/")) return new Response(JSON.stringify([task]));
      if (url.endsWith("/api/v1/planning/automation-policies/")) return new Response(JSON.stringify([]));
      if (url.includes("/capacity-forecast/")) {
        return new Response(JSON.stringify({ total_schedulable_capacity_minutes: 480, remaining_free_minutes: 480, committed_minutes: 0, unplanned_minutes: 60, risk: "within_capacity", reason_codes: [] }));
      }
      return new Response(JSON.stringify([]));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "高级规划设置" }));
    fireEvent.change(screen.getByLabelText(/开始（America\/New_York）/), {
      target: { value: "2026-03-08T02:30" },
    });
    await userEvent.click(screen.getByRole("button", { name: "生成草案" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/这个时间在 America\/New_York 不存在/);
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/planning/plans/"),
      expect.objectContaining({ method: "POST" }),
    );
  });
});
