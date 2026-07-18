import { describe, expect, it, vi } from "vitest";

import { parseEvent, streamAgentRun } from "../src/features/agent-runs/sse-client";

describe("agent SSE protocol", () => {
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
    await streaming;

    expect(events).toEqual(["agent.started", "message.completed"]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]?.[1]?.headers).toEqual(
      expect.objectContaining({ "Last-Event-ID": "1" }),
    );
    vi.useRealTimers();
  });
});
