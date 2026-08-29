import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InsightsPage } from "../src/pages/insights-page";

const insight = {
  id: "61111111-1111-4111-8111-111111111111",
  kind: "deadline_risk",
  severity: "medium",
  status: "open",
  title: "交付截止风险",
  summary: "当前计划可能无法覆盖剩余工作。",
  evidence: { task_id: "71111111-1111-4111-8111-111111111111", due_at: "2026-08-25T10:00:00Z" },
  deduplication_key: "deadline:61111111",
  detected_at: "2026-08-24T04:00:00Z",
  expires_at: "2026-08-25T04:00:00Z",
  snoozed_until: null,
  acted_at: null,
  attention_decision: "NORMAL_NOTIFICATION",
  attention_reason: "within_policy",
  attention_decided_at: "2026-08-24T04:00:00Z",
};

function renderPage(path = "/insights") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/insights/:insightId" element={<InsightsPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("InsightsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads a historical insight addressed by a notification deep link", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith(`/api/v1/insights/${insight.id}/`)) {
        return new Response(JSON.stringify({ ...insight, status: "false_positive" }));
      }
      if (url.endsWith("/api/v1/insights/")) return new Response(JSON.stringify([]));
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderPage(`/insights/${insight.id}`);

    expect(await screen.findByRole("heading", { name: insight.title })).toBeInTheDocument();
    expect(screen.getByText("状态：false_positive")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "处理" })).not.toBeInTheDocument();
  });

  it("records an explicit category disable action", async () => {
    let actionBody: unknown;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/api/v1/insights/${insight.id}/action/`)) {
        actionBody = JSON.parse(String(init?.body));
        return new Response(JSON.stringify({ ...insight, status: "false_positive" }));
      }
      if (url.endsWith("/api/v1/insights/")) return new Response(JSON.stringify([insight]));
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "关闭此类洞察" }));

    await waitFor(() => expect(actionBody).toEqual({
      action: "false_positive",
      disable_kind: true,
    }));
  });
});
