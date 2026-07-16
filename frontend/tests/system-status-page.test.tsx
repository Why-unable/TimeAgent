import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SystemStatusPage } from "../src/pages/system-status-page";

describe("SystemStatusPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: "ready",
            checks: { database: "ok", redis: "ok" },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
  });

  it("shows frontend and backend dependency status", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <SystemStatusPage />
      </QueryClientProvider>,
    );

    expect(screen.getByText("Frontend")).toBeInTheDocument();
    expect(await screen.findByText("Django")).toBeInTheDocument();
    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("Redis")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("正常")).toHaveLength(4);
    });
  });
});
