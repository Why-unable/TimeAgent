import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CalendarPage } from "../src/pages/calendar-page";

vi.mock("@fullcalendar/react", () => ({
  default: ({ events }: { events?: { id?: string; title?: string }[] }) => (
    <div data-testid="full-calendar">
      <span>月视图</span><span>周视图</span><span>日视图</span>
      {events?.map((event) => <span key={event.id}>{event.title}</span>)}
    </div>
  ),
}));

const preference = { timezone: "Asia/Shanghai", locale: "zh-CN" };
const calendarEvent = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "项目会议",
  description: "评审里程碑",
  start_at: "2026-07-20T01:00:00Z",
  end_at: "2026-07-20T02:00:00Z",
  timezone: "Asia/Shanghai",
  location: "会议室 A",
  status: "confirmed",
  visibility: "private",
  recurrence_rule: "",
  source: "local",
  external_id: "",
  created_by: 1,
  version: 3,
  created_at: "2026-07-19T01:00:00Z",
  updated_at: "2026-07-19T01:00:00Z",
};

function renderPage(children: ReactNode = <CalendarPage />) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}

describe("CalendarPage", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it("renders month, week and day calendar with event details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const body = String(input).includes("preferences") ? preference : [calendarEvent];
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    renderPage();

    expect(await screen.findByText("月视图")).toBeInTheDocument();
    expect(screen.getByText("周视图")).toBeInTheDocument();
    expect(screen.getByText("日视图")).toBeInTheDocument();
    expect(await screen.findAllByText("项目会议")).toHaveLength(2);
    expect(screen.getByText("会议室 A")).toBeInTheDocument();
  });

  it("creates an event using the configured user timezone", async () => {
    let createBody: Record<string, unknown> | undefined;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("preferences")) {
        return new Response(JSON.stringify(preference), { status: 200 });
      }
      if (init?.method === "POST") {
        createBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return new Response(JSON.stringify(calendarEvent), { status: 201 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await screen.findByText("当前范围暂无日程");

    await userEvent.click(screen.getByRole("button", { name: "新建日程" }));
    await userEvent.type(screen.getByLabelText("日程标题"), "客户沟通");
    fireEvent.change(screen.getByLabelText(/开始时间/), {
      target: { value: "2026-07-21T09:00" },
    });
    fireEvent.change(screen.getByLabelText(/结束时间/), {
      target: { value: "2026-07-21T10:00" },
    });
    await userEvent.click(screen.getByRole("button", { name: "创建日程" }));

    await waitFor(() => expect(createBody).toBeDefined());
    expect(createBody).toMatchObject({
      title: "客户沟通",
      start_at: "2026-07-21T01:00:00.000Z",
      end_at: "2026-07-21T02:00:00.000Z",
      timezone: "Asia/Shanghai",
    });
  });

  it("updates and cancels an event with its current version", async () => {
    const writes: { url: string; method?: string; body?: string }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("preferences")) return new Response(JSON.stringify(preference));
        if (init?.method === "PATCH" || init?.method === "DELETE") {
          writes.push({ url, method: init.method, body: String(init.body ?? "") });
          return init.method === "DELETE"
            ? new Response(null, { status: 204 })
            : new Response(JSON.stringify({ ...calendarEvent, title: "更新后的会议", version: 4 }));
        }
        return new Response(JSON.stringify([calendarEvent]));
      }),
    );
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /项目会议/ }));
    await userEvent.clear(screen.getByLabelText("日程标题"));
    await userEvent.type(screen.getByLabelText("日程标题"), "更新后的会议");
    await userEvent.click(screen.getByRole("button", { name: "保存修改" }));
    await waitFor(() => expect(writes[0]?.method).toBe("PATCH"));
    expect(writes[0]?.url).toContain("expected_version=3");

    await userEvent.click(await screen.findByRole("button", { name: /项目会议/ }));
    await userEvent.click(screen.getByRole("button", { name: "取消日程" }));
    await userEvent.click(screen.getByRole("button", { name: "确认取消" }));
    await waitFor(() => expect(writes[1]?.method).toBe("DELETE"));
    expect(writes[1]?.url).toContain("expected_version=3");
  });
});
