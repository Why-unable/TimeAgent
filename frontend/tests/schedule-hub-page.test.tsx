import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { ScheduleHubPage } from "../src/pages/schedule-hub-page";

const preference = { timezone: "Asia/Shanghai", locale: "zh-CN" };
const event = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "清晨项目评审",
  start_at: "2026-10-04T18:30:00Z",
  end_at: "2026-10-04T19:30:00Z",
  timezone: "Asia/Shanghai",
  location: "会议室 A",
  status: "confirmed",
  source: "local",
};
const plannedTask = {
  id: "21111111-1111-4111-8111-111111111111",
  title: "准备评审材料",
  status: "pending",
  priority: "high",
  due_at: "2026-10-05T12:00:00Z",
  planned_start_at: "2026-10-04T20:00:00Z",
  planned_end_at: "2026-10-04T20:30:00Z",
};
const unplannedTask = {
  ...plannedTask,
  id: "31111111-1111-4111-8111-111111111111",
  title: "整理项目记录",
  due_at: null,
  planned_start_at: null,
  planned_end_at: null,
};
const requestedUrls: string[] = [];

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/schedule"]}>
      <QueryClientProvider client={client}><ScheduleHubPage /></QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("ScheduleHubPage", () => {
  beforeEach(() => {
    requestedUrls.length = 0;
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-10-04T16:00:00Z"));
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requestedUrls.push(url);
      const body = url.includes("preferences")
        ? preference
        : url.includes("/events/")
          ? [event]
          : [plannedTask, unplannedTask];
      return new Response(JSON.stringify(body), { status: 200 });
    }));
  });

  it("shows events, scheduled task blocks and unplanned tasks as separate facts", async () => {
    renderPage();
    expect(await screen.findByText("清晨项目评审")).toBeInTheDocument();
    expect(screen.getByText("02:30")).toBeInTheDocument();
    expect(screen.getByText(/2026年10月5日/)).toBeInTheDocument();
    expect(screen.getByText("准备评审材料")).toBeInTheDocument();
    expect(screen.getByText("整理项目记录")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /准备评审材料/ }).textContent).toContain("计划任务");
    expect(screen.getByText(/日程和计划任务按/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "让助理起草安排" })).toHaveAttribute("href", "/planning");
    expect(screen.getByRole("link", { name: /^日历$/ })).toHaveAttribute(
      "href",
      "/calendar?date=2026-10-05",
    );
    const eventRequest = requestedUrls.find((url) => url.includes("/api/v1/events/"));
    expect(eventRequest).toBeDefined();
    const eventQuery = new URL(eventRequest!, "http://localhost").searchParams;
    expect(eventQuery.get("ends_after")).toBe("2026-10-03T12:00:00.000Z");
    expect(eventQuery.get("starts_before")).toBe("2026-10-13T12:00:00.000Z");
  });

  it("pages weeks and changes the selected date without changing business data", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPage();
    await screen.findByText("清晨项目评审");
    await user.click(screen.getByRole("button", { name: "下一周" }));
    expect(screen.getByRole("button", { name: /2026年10月12日/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("2026年10月12日星期一")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "本周" }));
    expect(screen.getByRole("button", { name: /2026年10月5日/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("provides separate event and task retry actions", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("preferences")) return new Response(JSON.stringify(preference));
      if (url.includes("/events/")) return new Response("{}", { status: 503 });
      return new Response(JSON.stringify([unplannedTask]));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    expect(await screen.findByText("当天日程暂时无法读取。")).toBeInTheDocument();
    expect(screen.getByText("整理项目记录")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "重试" })).toHaveLength(1);
  });
});
