import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { RemindersPage } from "../src/pages/reminders-page";

const preference = {
  timezone: "Asia/Shanghai",
  locale: "zh-CN",
};

const failedReminder = {
  id: "11111111-1111-4111-8111-111111111111",
  target_type: "custom",
  target_id: null,
  title: "提交项目报告",
  trigger_at: "2026-07-17T07:00:00Z",
  timezone: "Asia/Shanghai",
  channel: "console",
  status: "failed",
  deduplication_key: "fixed-key",
  queued_at: "2026-07-17T06:59:00Z",
  sent_at: null,
  retry_count: 2,
  failure_reason: "console unavailable",
  created_at: "2026-07-17T06:00:00Z",
  updated_at: "2026-07-17T07:00:00Z",
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <RemindersPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("RemindersPage", () => {
  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024 });
    vi.spyOn(crypto, "randomUUID").mockReturnValue(
      "22222222-2222-4222-8222-222222222222",
    );
  });

  it("renders the shared 日程/任务/规划/提醒 workspace tabs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const body = url.includes("preferences") ? preference : [];
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
    renderPage();
    const nav = await screen.findByRole("navigation", { name: "时间管理工作区" });
    expect(nav).toBeInTheDocument();
    expect(nav.querySelectorAll("a")).toHaveLength(4);
    expect(nav).toHaveTextContent("规划");
  });

  it("shows reminder status, retry count and failure reason", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const body = url.includes("preferences") ? preference : [failedReminder];
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    renderPage();

    expect(await screen.findByText("提交项目报告")).toBeInTheDocument();
    expect(screen.getByText("发送失败")).toBeInTheDocument();
    expect(screen.getByText("已重试 2 次")).toBeInTheDocument();
    expect(screen.getByText("console unavailable")).toBeInTheDocument();
    expect(screen.getByText(/2026\/07\/17 15:00/)).toBeInTheDocument();
  });

  it("creates a reminder using UTC and a stable idempotency key", async () => {
    let createBody: Record<string, unknown> | undefined;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("preferences")) {
        return new Response(JSON.stringify(preference), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (init?.method === "POST") {
        createBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return new Response(JSON.stringify(failedReminder), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await screen.findByText(/还没有提醒/);

    await userEvent.type(screen.getByLabelText("提醒内容"), "提交 API 报告");
    fireEvent.change(screen.getByLabelText(/提醒时间/), {
      target: { value: "2026-07-17T15:00" },
    });
    await userEvent.click(screen.getByRole("button", { name: "新建提醒" }));

    await waitFor(() => expect(createBody).toBeDefined());
    expect(createBody).toMatchObject({
      title: "提交 API 报告",
      trigger_at: "2026-07-17T07:00:00.000Z",
      timezone: "Asia/Shanghai",
      channel: "console",
      target_type: "custom",
      deduplication_key: "22222222-2222-4222-8222-222222222222",
    });
  });

  it("explains a skipped daylight-saving time and does not submit it", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("preferences")
        ? { ...preference, timezone: "America/New_York" }
        : [];
      return new Response(JSON.stringify(body), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await screen.findByText(/还没有提醒/);

    await userEvent.type(screen.getByLabelText("提醒内容"), "调夏令时提醒");
    fireEvent.change(screen.getByLabelText(/提醒时间/), {
      target: { value: "2026-03-08T02:30" },
    });
    await userEvent.click(screen.getByRole("button", { name: "新建提醒" }));

    expect(await screen.findByText(/这个时间在 America\/New_York 不存在/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/reminders/"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("cancels a cancellable reminder", async () => {
    let deleteUrl = "";
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("preferences")) {
        return new Response(JSON.stringify(preference), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (init?.method === "DELETE") {
        deleteUrl = url;
        return new Response(null, { status: 204 });
      }
      return new Response(JSON.stringify([failedReminder]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    await userEvent.click(
      await screen.findByRole("button", { name: "取消提醒：提交项目报告" }),
    );

    await waitFor(() =>
      expect(deleteUrl).toContain(`/api/v1/reminders/${failedReminder.id}/`),
    );
  });

  it("opens a focused mobile creation sheet and announces success after saving", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 393 });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("preferences")) return new Response(JSON.stringify(preference), { status: 200 });
      if (init?.method === "POST") return new Response(JSON.stringify(failedReminder), { status: 201 });
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await screen.findByText(/还没有提醒/);

    await userEvent.click(screen.getByRole("button", { name: "打开新建提醒" }));
    const dialog = screen.getByRole("dialog", { name: "新建提醒" });
    expect(dialog).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("提醒内容"), "项目复盘");
    fireEvent.change(screen.getByLabelText(/提醒时间/), { target: { value: "2026-07-17T15:00" } });
    await userEvent.click(screen.getByRole("button", { name: "创建提醒" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/reminders/"),
      expect.objectContaining({ method: "POST" }),
    ));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "新建提醒" })).not.toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("提醒已创建");
  });

  it("shows a cancelled-only history instead of a blank list", async () => {
    const cancelledReminder = { ...failedReminder, status: "cancelled" };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      return new Response(JSON.stringify(url.includes("preferences") ? preference : [cancelledReminder]), { status: 200 });
    }));
    renderPage();
    expect(await screen.findByText("已取消的提醒")).toBeInTheDocument();
    expect(screen.getByText("提交项目报告")).toBeInTheDocument();
    expect(screen.queryByText(/还没有提醒/)).not.toBeInTheDocument();
  });

  it("offers a retry when the reminder list request fails", async () => {
    let listAttempts = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("preferences")) return new Response(JSON.stringify(preference), { status: 200 });
      if (!url.includes("/api/v1/reminders/")) return new Response(JSON.stringify([]), { status: 200 });
      listAttempts += 1;
      if (listAttempts === 1) return new Response(JSON.stringify({ detail: "offline" }), { status: 503 });
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    const retry = await screen.findByRole("button", { name: "重试读取" });
    expect(screen.queryByText(/还没有提醒/)).not.toBeInTheDocument();
    await userEvent.click(retry);
    expect(await screen.findByText(/还没有提醒/)).toBeInTheDocument();
    expect(listAttempts).toBe(2);
  });
});
