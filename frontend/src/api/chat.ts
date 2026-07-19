import { apiRequest } from "./client";

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export type PersistedRunStatus = "pending" | "running" | "waiting_approval" | "completed" | "failed" | "cancelled";

export interface AgentRun {
  id: string;
  conversation_id: string;
  operation_id: string;
  request_id: string;
  status: PersistedRunStatus;
  input_message: string;
  final_response: string;
  error: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  runs: AgentRun[];
}

export function listConversations() {
  return apiRequest<Conversation[]>("/api/v1/chat/conversations/");
}

export function getConversation(conversationId: string) {
  return apiRequest<ConversationDetail>(`/api/v1/chat/conversations/${conversationId}/`);
}

export function createConversation(title = "") {
  return apiRequest<Conversation>("/api/v1/chat/conversations/", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export function sendChatMessage(conversationId: string, message: string) {
  return apiRequest<AgentRun>("/api/v1/chat/messages/", {
    method: "POST",
    body: JSON.stringify({
      conversation_id: conversationId,
      message,
      operation_id: crypto.randomUUID(),
    }),
  });
}

export function cancelAgentRun(runId: string) {
  return apiRequest<AgentRun>(`/api/v1/chat/runs/${runId}/cancel/`, { method: "POST" });
}
