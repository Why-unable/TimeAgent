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
    vi.spyOn(crypto, "randomUUID").mockReturnValue(
      "22222222-2222-4222-8222-222222222222",
    );
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
    await screen.findByText("暂无提醒");

    await userEvent.type(screen.getByLabelText("提醒内容"), "提交 API 报告");
    fireEvent.change(screen.getByLabelText(/提醒时间/), {
      target: { value: "2026-07-17T15:00" },
    });
    await userEvent.click(screen.getByRole("button", { name: "创建提醒" }));

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
});
