import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearAuthToken,
  resetTokenStore,
  setTokenStore,
} from "../src/api/auth-token";
import { parseEvent, streamAgentRun } from "../src/features/agent-runs/sse-client";

describe("agent SSE protocol", () => {
  afterEach(async () => {
    await clearAuthToken();
    resetTokenStore();
  });

  it("parses cursor, typed event and multiline JSON data", () => {
    const event = parseEvent(
      'id: 7\nevent: tool.completed\ndata: {"tool_name":\ndata: "list_events"}',
    );

    expect(event).toEqual({
      id: "7",
      type: "tool.completed",
      data: { tool_name: "list_events" },
    });
  });

  it("ignores heartbeat frames without data", () => {
    expect(parseEvent(": heartbeat")).toBeNull();
  });

  it("reconnects from the latest cursor after a premature end", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(
        'id: 1\nevent: agent.started\ndata: {"run_id":"run-1"}\n\n',
        { headers: { "Content-Type": "text/event-stream" } },
      ))
      .mockResolvedValueOnce(new Response(
        'id: 2\nevent: message.completed\ndata: {"content":"done"}\n\n',
        { headers: { "Content-Type": "text/event-stream" } },
      ));
    vi.stubGlobal("fetch", fetchMock);
    const events: string[] = [];

    const streaming = streamAgentRun("run-1", (event) => events.push(event.type));
    await vi.advanceTimersByTimeAsync(250);
    await expect(streaming).resolves.toBe("2");

    expect(events).toEqual(["agent.started", "message.completed"]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]?.[1]?.headers).toEqual(
      expect.objectContaining({ "Last-Event-ID": "1" }),
    );
    vi.useRealTimers();
  });

  it("sends the auth token and omits cookies when a token is present", async () => {
    let stored: string | null = null;
    setTokenStore({
      load: async () => stored,
      save: async (token) => {
        stored = token;
      },
      clear: async () => {
        stored = null;
      },
    });
    const { setAuthToken } = await import("../src/api/auth-token");
    await setAuthToken("native-token-abc");

    const fetchMock = vi.fn().mockResolvedValue(
      new Response('id: 1\nevent: message.completed\ndata: {"content":"ok"}\n\n', {
        headers: { "Content-Type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await streamAgentRun("run-1", () => {});

    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.credentials).toBe("omit");
    expect(init?.headers).toEqual(
      expect.objectContaining({ Authorization: "Token native-token-abc" }),
    );
  });
});
