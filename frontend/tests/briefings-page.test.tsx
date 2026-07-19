import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BriefingsPage } from "../src/pages/briefings-page";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BriefingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BriefingsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("launches a manual briefing in its own conversation", async () => {
    const definition = {
      id: "11111111-1111-4111-8111-111111111111",
      name: "每日简报",
      enabled_sections: ["calendar", "tasks"],
      locale: "",
      timezone: "",
      style: "balanced",
      include_empty_sections: false,
      is_active: true,
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    };
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, init });
      if (url.endsWith("/definitions/")) return new Response(JSON.stringify([definition]));
      if (url.endsWith("/runs/") && (init?.method ?? "GET") === "GET") {
        return new Response(JSON.stringify([]));
      }
      if (url.endsWith("/runs/") && init?.method === "POST") {
        return new Response(JSON.stringify({
          conversation: {
            id: "22222222-2222-4222-8222-222222222222",
            title: "2026-07-19 · 每日简报",
            kind: "manual_briefing",
            created_at: "2026-07-19T00:00:00Z",
            updated_at: "2026-07-19T00:00:00Z",
          },
          agent_run: {},
        }), { status: 202 });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderPage();
    expect(await screen.findByRole("option", { name: "每日简报" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "立即生成" }));

    const launchRequest = requests.find((item) => item.init?.method === "POST");
    expect(launchRequest).toBeDefined();
    expect(JSON.parse(String(launchRequest?.init?.body))).toEqual(expect.objectContaining({
      definition_id: definition.id,
    }));
  });
});
