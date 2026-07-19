import { apiRequest } from "./client";

export type ActionProposalStatus =
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "executing"
  | "executed"
  | "failed"
  | "expired";

export interface ActionProposal {
  id: string;
  conversation_id: string;
  agent_run_id: string;
  original_request: string;
  explanation: string;
  action_type: string;
  action_payload: Record<string, unknown>;
  original_payload: Record<string, unknown>;
  display_context: Record<string, unknown>;
  risk_level: "high";
  status: ActionProposalStatus;
  requires_approval: boolean;
  version: number;
  expires_at: string;
  decided_at: string | null;
  approved_at: string | null;
  resumed_at: string | null;
  executed_at: string | null;
  decision_reason: string;
  execution_result: unknown;
  error: string;
  created_at: string;
  updated_at: string;
}

export interface ProposalDecisionResponse {
  proposal: ActionProposal;
  resume_queued: boolean;
}

export function listActionProposals(status?: ActionProposalStatus) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<ActionProposal[]>(`/api/v1/action-proposals/${query}`);
}

export function getActionProposal(proposalId: string) {
  return apiRequest<ActionProposal>(`/api/v1/action-proposals/${proposalId}/`);
}

export function decideActionProposal(
  proposal: ActionProposal,
  decision: "approve" | "edit" | "reject",
  options: { actionPayload?: Record<string, unknown>; reason?: string } = {},
) {
  return apiRequest<ProposalDecisionResponse>(
    `/api/v1/action-proposals/${proposal.id}/${decision}/`,
    {
      method: "POST",
      body: JSON.stringify({
        expected_version: proposal.version,
        operation_id: crypto.randomUUID(),
        reason: options.reason ?? "",
        ...(decision === "edit" ? { action_payload: options.actionPayload } : {}),
      }),
    },
  );
}
