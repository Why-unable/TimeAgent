import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Task } from "../src/api/tasks";
import { DayClosing } from "../src/components/today/day-closing";

const placedTaskId = "21111111-1111-4111-8111-111111111111";
const unplacedTaskId = "31111111-1111-4111-8111-111111111111";

const unfinishedTasks = [
  { id: placedTaskId, title: "准备产品复盘", estimated_minutes: 45 },
  { id: unplacedTaskId, title: "整理研究资料", estimated_minutes: 60 },
] as Task[];

const completedTasks = [
  { id: "41111111-1111-4111-8111-111111111111", title: "完成访谈纪要" },
] as Task[];

function renderClosing(date = "2026-10-03", timezone = "Asia/Shanghai") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <DayClosing
          date={date}
          timezone={timezone}
          unfinishedTasks={unfinishedTasks}
          completedTasks={completedTasks}
        />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("DayClosing", () => {
  beforeEach(() => window.sessionStorage.clear());

  it("creates a timezone-correct draft and asks before removing unplaced work", async () => {
    const requests: Array<{ url: string; method: string; body: Record<string, unknown> }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
      if (method === "POST") requests.push({ url, method, body });
      if (url.endsWith("/abandon/")) {
        return new Response(JSON.stringify({ id: "plan-1", status: "abandoned", version: 2 }));
      }
      if (url.endsWith("/plans/")) {
        return new Response(JSON.stringify({
          id: "plan-1",
          status: "draft",
          version: 1,
          items: [
            { kind: "task", task_id: placedTaskId, state: "placed" },
            { kind: "task", task_id: unplacedTaskId, state: "unplaced", reason_codes: ["insufficient_free_capacity"] },
            { kind: "plan_evidence", state: "placed" },
          ],
        }));
      }
      return new Response("[]");
    }));

    renderClosing();
    expect(screen.getByText("已完成 1 项")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "整理明天" }));

    const placedCheckbox = screen.getByRole("checkbox", { name: /准备产品复盘/ });
    const unplacedCheckbox = screen.getByRole("checkbox", { name: /整理研究资料/ });
    await userEvent.click(placedCheckbox);
    await userEvent.click(unplacedCheckbox);
    await userEvent.click(screen.getByRole("button", { name: /为 2026年10月4日.*生成草案/ }));

    expect(await screen.findByText("明日草案已生成", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText(/整理研究资料：没有找到符合当前日程/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "手动调整草案" })).toHaveAttribute("href", "/planning?plan_id=plan-1");
    expect(placedCheckbox).toBeDisabled();
    expect(unplacedCheckbox).toBeDisabled();

    const createRequest = requests.find((request) => request.url.endsWith("/plans/"));
    expect(createRequest?.body).toMatchObject({
      task_ids: [placedTaskId, unplacedTaskId],
      range_start: "2026-10-03T16:00:00.000Z",
      range_end: "2026-10-04T16:00:00.000Z",
      strategy: "plan_tasks_only",
      ordering: "priority_deadline",
    });
    expect(createRequest?.body.operation_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);

    await userEvent.click(screen.getByRole("button", { name: "移除未安排项并重新选择" }));
    await waitFor(() => expect(requests.some((request) => request.url.endsWith("/plan-1/abandon/"))).toBe(true));
    expect(requests.find((request) => request.url.endsWith("/plan-1/abandon/"))?.body)
      .toEqual({ expected_version: 1 });
    expect(placedCheckbox).toBeChecked();
    expect(unplacedCheckbox).not.toBeChecked();
    expect(placedCheckbox).toBeEnabled();
    expect(unplacedCheckbox).toBeEnabled();
    expect(screen.getByText("草案已放弃；任务仍保留在任务列表中。")).toBeInTheDocument();
  });

  it("asks how to handle unplaced work and lets the user revise task estimates before replanning", async () => {
    const requests: Array<{ url: string; method: string; body: Record<string, unknown> }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
      if (method !== "GET") requests.push({ url, method, body });
      if (url.endsWith("/abandon/")) {
        return new Response(JSON.stringify({ id: "plan-1", status: "abandoned", version: 2 }));
      }
      if (url.endsWith("/plans/")) {
        return new Response(JSON.stringify({
          id: "plan-1",
          status: "draft",
          version: 1,
          items: [
            { kind: "task", task_id: placedTaskId, state: "placed" },
            { kind: "task", task_id: unplacedTaskId, state: "unplaced", reason_codes: ["insufficient_free_capacity"] },
            { kind: "plan_evidence", state: "placed" },
          ],
        }));
      }
      return new Response(JSON.stringify({}));
    }));

    renderClosing();
    await userEvent.click(screen.getByRole("button", { name: "整理明天" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /准备产品复盘/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /整理研究资料/ }));
    await userEvent.click(screen.getByRole("button", { name: /为 2026年10月4日.*生成草案/ }));
    const decision = await screen.findByRole("region", { name: "明日安排取舍" });

    await userEvent.click(within(decision).getByRole("button", { name: "保留未安排项" }));
    expect(within(decision).getByRole("status")).toHaveTextContent("正式任务和日程没有改变");
    await userEvent.click(within(decision).getByRole("button", { name: "调整估时或缓冲" }));
    expect(await screen.findByLabelText("预计时长（分钟）")).toHaveValue(60);
    await userEvent.clear(screen.getByLabelText("预计时长（分钟）"));
    await userEvent.type(screen.getByLabelText("预计时长（分钟）"), "45");
    await userEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText(/任务信息已更新。重新生成草案会使用新的预计时长和缓冲/)).toBeInTheDocument();
    const abandonIndex = requests.findIndex((request) => request.url.endsWith("/plan-1/abandon/"));
    const updateIndex = requests.findIndex((request) => request.method === "PATCH" && request.url.endsWith(`/${unplacedTaskId}/`));
    expect(abandonIndex).toBeGreaterThanOrEqual(0);
    expect(updateIndex).toBeGreaterThan(abandonIndex);
    expect(requests[updateIndex]?.body).toMatchObject({ estimated_minutes: 45 });
    expect(screen.getByRole("checkbox", { name: /准备产品复盘/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /整理研究资料/ })).toBeChecked();
  });

  it("abandons a completed draft before clearing the task selection", async () => {
    const requests: Array<{ url: string; method: string; body: Record<string, unknown> }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
      if (method !== "GET") requests.push({ url, method, body });
      if (url.endsWith("/abandon/")) {
        return new Response(JSON.stringify({ id: "plan-1", status: "abandoned", version: 2 }));
      }
      if (url.endsWith("/plans/")) {
        return new Response(JSON.stringify({
          id: "plan-1",
          status: "draft",
          version: 1,
          items: [{ kind: "task", task_id: placedTaskId, state: "placed" }],
        }));
      }
      return new Response("[]");
    }));

    renderClosing();
    await userEvent.click(screen.getByRole("button", { name: "整理明天" }));
    const placedCheckbox = screen.getByRole("checkbox", { name: /准备产品复盘/ });
    await userEvent.click(placedCheckbox);
    await userEvent.click(screen.getByRole("button", { name: /为 2026年10月4日.*生成草案/ }));
    expect(await screen.findByText("明日草案已生成", { selector: "p" })).toBeInTheDocument();
    expect(placedCheckbox).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "放弃草案并重新选择" }));

    await waitFor(() => expect(requests.some((request) => request.url.endsWith("/plan-1/abandon/"))).toBe(true));
    expect(placedCheckbox).not.toBeChecked();
    expect(placedCheckbox).toBeEnabled();
    expect(screen.getByText("草案已放弃；任务仍保留在任务列表中。")).toBeInTheDocument();
  });

  it("reuses the operation ID after an ambiguous network failure", async () => {
    const operationIds: unknown[] = [];
    let planRequests = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/plans/") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        operationIds.push(body.operation_id);
        planRequests += 1;
        if (planRequests === 1) return new Response("temporarily unavailable", { status: 503 });
        return new Response(JSON.stringify({ id: "retry-plan", items: [] }));
      }
      return new Response("[]");
    }));

    const firstRender = renderClosing();
    await userEvent.click(screen.getByRole("button", { name: "整理明天" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /准备产品复盘/ }));
    const createButton = screen.getByRole("button", { name: /为 2026年10月4日.*生成草案/ });
    await userEvent.click(createButton);
    expect(await screen.findByRole("alert")).toHaveTextContent("明日草案暂时没有生成");
    firstRender.unmount();
    renderClosing();
    const restoredCreateButton = screen.getByRole("button", { name: /为 2026年10月4日.*生成草案/ });
    expect(screen.getByRole("checkbox", { name: /准备产品复盘/ })).toBeChecked();
    await userEvent.click(restoredCreateButton);

    await waitFor(() => expect(planRequests).toBe(2));
    expect(operationIds[0]).toBe(operationIds[1]);
  });

  it("creates a new operation ID after changing a failed request's selection", async () => {
    const operationIds: unknown[] = [];
    let planRequests = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/plans/") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        operationIds.push(body.operation_id);
        planRequests += 1;
        if (planRequests === 1) return new Response("temporarily unavailable", { status: 503 });
        return new Response(JSON.stringify({ id: "selection-changed-plan", status: "draft", version: 1, items: [] }));
      }
      return new Response("[]");
    }));

    renderClosing();
    await userEvent.click(screen.getByRole("button", { name: "整理明天" }));
    const first = screen.getByRole("checkbox", { name: /准备产品复盘/ });
    const second = screen.getByRole("checkbox", { name: /整理研究资料/ });
    await userEvent.click(first);
    await userEvent.click(screen.getByRole("button", { name: /为 2026年10月4日.*生成草案/ }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await userEvent.click(first);
    await userEvent.click(second);
    await userEvent.click(screen.getByRole("button", { name: /为 2026年10月4日.*生成草案/ }));

    await waitFor(() => expect(planRequests).toBe(2));
    expect(operationIds[0]).not.toBe(operationIds[1]);
  });

  it("restores a draft and selected tasks after remount", async () => {
    let planGets = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/plans/") && init?.method === "POST") {
        return new Response(JSON.stringify({
          id: "restored-plan",
          status: "draft",
          version: 1,
          items: [{ kind: "task", task_id: placedTaskId, state: "placed" }],
        }));
      }
      if (url.endsWith("/plans/restored-plan/")) {
        planGets += 1;
        return new Response(JSON.stringify({
          id: "restored-plan",
          status: "draft",
          version: 1,
          items: [{ kind: "task", task_id: placedTaskId, state: "placed" }],
        }));
      }
      return new Response("[]");
    }));

    const firstRender = renderClosing();
    await userEvent.click(screen.getByRole("button", { name: "整理明天" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /准备产品复盘/ }));
    await userEvent.click(screen.getByRole("button", { name: /为 2026年10月4日.*生成草案/ }));
    expect(await screen.findByText("明日草案已生成", { selector: "p" })).toBeInTheDocument();
    firstRender.unmount();

    renderClosing();
    expect(await screen.findByRole("button", { name: "明日草案已生成" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /准备产品复盘/ })).toBeChecked();
    expect(await screen.findByRole("link", { name: "检查草案" })).toHaveAttribute("href", "/planning?plan_id=restored-plan");
    expect(planGets).toBe(1);
  });

  it("uses local midnight across the Los Angeles DST transition", async () => {
    let body: Record<string, unknown> | undefined;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/plans/") && init?.method === "POST") {
        body = JSON.parse(String(init.body)) as Record<string, unknown>;
        return new Response(JSON.stringify({ id: "dst-plan", status: "draft", version: 1, items: [] }));
      }
      return new Response("[]");
    }));

    renderClosing("2026-03-07", "America/Los_Angeles");
    await userEvent.click(screen.getByRole("button", { name: "整理明天" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /准备产品复盘/ }));
    await userEvent.click(screen.getByRole("button", { name: /为 2026年3月8日.*生成草案/ }));
    await waitFor(() => expect(body).toBeDefined());
    expect(body).toMatchObject({
      range_start: "2026-03-08T08:00:00.000Z",
      range_end: "2026-03-09T07:00:00.000Z",
    });
  });
});
