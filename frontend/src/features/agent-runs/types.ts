/**
 * UI-neutral placeholders for Phase 4 graph execution state.
 *
 * These are not transport contracts. When the Chat/SSE API is introduced,
 * request, response, and event payload types must come from generated API
 * contracts instead of being duplicated here.
 */
export const AGENT_RUN_STATUSES = [
  "idle",
  "connecting",
  "running",
  "waiting_for_tool",
  "waiting_for_approval",
  "handing_off",
  "completed",
  "failed",
  "cancelled",
] as const;

export type AgentRunStatus = (typeof AGENT_RUN_STATUSES)[number];

export interface PendingGraphInterrupt {
  id: string;
  value: unknown;
}

export interface AgentRunFailure {
  code: string;
  message: string;
  retryable: boolean;
}

export interface AgentRunSnapshot {
  status: AgentRunStatus;
  runId: string | null;
  conversationId: string | null;
  threadId: string | null;
  activeAgent: string | null;
  currentMessageId: string | null;
  pendingInterrupts: readonly PendingGraphInterrupt[];
  lastEventId: string | null;
  failure: AgentRunFailure | null;
}
