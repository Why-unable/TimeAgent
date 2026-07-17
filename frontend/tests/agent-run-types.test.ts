import { describe, expect, it } from "vitest";

import {
  AGENT_RUN_STATUSES,
  type AgentRunSnapshot,
} from "../src/features/agent-runs/types";

describe("agent run state contract", () => {
  it("keeps the reserved frontend lifecycle states explicit", () => {
    expect(AGENT_RUN_STATUSES).toEqual([
      "idle",
      "connecting",
      "running",
      "waiting_for_tool",
      "waiting_for_approval",
      "handing_off",
      "completed",
      "failed",
      "cancelled",
    ]);
  });

  it("represents an interrupted run without assuming an SSE payload shape", () => {
    const snapshot = {
      status: "waiting_for_approval",
      runId: "run-1",
      conversationId: "conversation-1",
      threadId: "conversation-1",
      activeAgent: "time_steward_agent",
      currentMessageId: null,
      pendingInterrupts: [
        {
          id: "interrupt-1",
          value: { action: "review" },
        },
      ],
      lastEventId: null,
      failure: null,
    } satisfies AgentRunSnapshot;

    expect(snapshot.pendingInterrupts[0]?.value).toEqual({ action: "review" });
  });
});
