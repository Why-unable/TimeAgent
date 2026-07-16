import { describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest } from "../src/api/client";

describe("apiRequest", () => {
  it("returns parsed JSON and sends a request id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "alive" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/health/live")).resolves.toEqual({ status: "alive" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/health/live",
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.objectContaining({ "X-Request-ID": expect.any(String) }),
      }),
    );
  });

  it("maps non-success responses to ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 503 })));

    await expect(apiRequest("/health/ready")).rejects.toBeInstanceOf(ApiError);
  });
});

