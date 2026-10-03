import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { MorningBrief } from "../src/components/today/morning-brief";

function renderBrief() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/today"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/chat/:conversationId" element={<p>已打开晨间简报会话</p>} />
          <Route path="*" element={<MorningBrief targetDate="2026-10-03" />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("MorningBrief", () => {
  it("launches the selected date briefing and opens its workflow conversation", async () => {
    let launchBody: Record<string, unknown> | undefined;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/briefings/runs/") && init?.method === "POST") {
        launchBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return new Response(JSON.stringify({
          conversation: { id: "71111111-1111-4111-8111-111111111111" },
          agent_run: { id: "81111111-1111-4111-8111-111111111111" },
        }));
      }
      return new Response(JSON.stringify([]));
    }));

    renderBrief();
    await userEvent.click(await screen.findByRole("button", { name: "生成今日日程简报" }));

    expect(await screen.findByText("已打开晨间简报会话")).toBeInTheDocument();
    expect(launchBody).toMatchObject({ definition_id: null, target_date: "2026-10-03" });
    expect(launchBody?.operation_id).toMatch(/^[0-9a-f-]{36}$/i);
  });

  it("shows a short real-run preview when today's briefing already exists", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([{
      id: "91111111-1111-4111-8111-111111111111",
      target_date: "2026-10-03",
      status: "completed",
      conversation_id: "a1111111-1111-4111-8111-111111111111",
      rendered_markdown: "## 今日重点\n- 先完成发布复盘\n- 下午有项目评审",
    }]))));

    renderBrief();

    expect(await screen.findByText("今日日程简报已准备好。")).toBeInTheDocument();
    expect(screen.getByText("今日重点 先完成发布复盘")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看简报" })).toHaveAttribute("href", "/chat/a1111111-1111-4111-8111-111111111111");
  });
});
