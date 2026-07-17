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
    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = request.headers as Headers;
    expect(request.credentials).toBe("same-origin");
    expect(headers.get("X-Request-ID")).toEqual(expect.any(String));
    expect(headers.get("Accept")).toBe("application/json");
  });

  it("maps non-success responses to ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 503 })));

    await expect(apiRequest("/health/ready")).rejects.toBeInstanceOf(ApiError);
  });

  it("preserves a structured API error detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Event version conflict" }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(apiRequest("/api/v1/events/example/")).rejects.toMatchObject({
      message: "Event version conflict",
      status: 409,
    });
  });

  it("adds JSON and CSRF headers to write requests", async () => {
    Object.defineProperty(document, "cookie", {
      configurable: true,
      value: "csrftoken=phase1-token",
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ timezone: "Asia/Shanghai" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("/api/v1/preferences/me/", {
      method: "PATCH",
      body: JSON.stringify({ timezone: "Asia/Shanghai" }),
    });

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = request.headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-CSRFToken")).toBe("phase1-token");
  });
});
