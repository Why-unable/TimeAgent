import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

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

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <PlanningPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("PlanningPage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-07-20T01:00:00Z"));
  });

  afterEach(() => vi.useRealTimers());

  it("generates an explainable draft and applies it once", async () => {
    let createBody: Record<string, unknown> | undefined;
    let applyBody: Record<string, unknown> | undefined;
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
        if (url.includes("/apply/") && init?.method === "POST") {
          applyBody = JSON.parse(String(init.body)) as Record<string, unknown>;
          return new Response(JSON.stringify({
            id: "41111111-1111-4111-8111-111111111111",
            strategy: "plan_tasks_only",
            status: "applied",
            version: 2,
            created_at: "2026-07-20T01:00:00Z",
            applied_at: "2026-07-20T01:01:00Z",
            items: [],
          }), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }),
    );
    renderPage();

    expect(await screen.findByText("容量超载")).toBeInTheDocument();
    expect(screen.getByText("未安排任务所需时间超过可用容量")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("checkbox", { name: /准备发布报告/ }));
    await userEvent.click(screen.getByRole("button", { name: "生成草案" }));

    expect(await screen.findByText("已安排")).toBeInTheDocument();
    expect(createBody).toMatchObject({ task_ids: [task.id], strategy: "plan_tasks_only" });
    await userEvent.click(screen.getByRole("button", { name: "锁定计划块：准备发布报告" }));
    await waitFor(() => expect(editBody).toMatchObject({
      expected_version: 1,
      items: [{ task_id: task.id, locked: true }],
    }));
    expect(await screen.findByRole("button", { name: "解锁计划块：准备发布报告" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "验证" }));
    expect(await screen.findByText("草案仍然有效。")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "确认应用" }));
    await waitFor(() => expect(applyBody).toEqual({ expected_version: 2 }));
    expect(await screen.findByText("计划已应用。")).toBeInTheDocument();
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

    await userEvent.click(await screen.findByRole("checkbox", { name: /准备发布报告/ }));
    await userEvent.click(screen.getByRole("button", { name: "比较两种方案" }));
    expect(await screen.findByRole("button", { name: /长任务优先/ })).toBeInTheDocument();
    const checkboxes = screen.getAllByRole("checkbox", { name: /准备发布报告/ });
    await userEvent.click(checkboxes[1]);
    await userEvent.click(screen.getByRole("button", { name: "只重生成选中项" }));
    await waitFor(() => expect(regenerateBody).toMatchObject({
      expected_version: 1,
      task_ids: [task.id],
      ordering: "priority_deadline",
    }));
  });
});
