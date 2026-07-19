import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  decideActionProposal,
  listActionProposals,
  type ActionProposal,
  type ActionProposalStatus,
} from "../../api/action-proposals";

export const approvalQueryKey = ["action-proposals"] as const;

export function useActionProposals(status?: ActionProposalStatus) {
  return useQuery({
    queryKey: [...approvalQueryKey, status ?? "all"],
    queryFn: () => listActionProposals(status),
    refetchInterval: 15_000,
    retry: false,
  });
}
export function useProposalDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      proposal,
      decision,
      actionPayload,
      reason,
    }: {
      proposal: ActionProposal;
      decision: "approve" | "edit" | "reject";
      actionPayload?: Record<string, unknown>;
      reason?: string;
    }) => decideActionProposal(proposal, decision, { actionPayload, reason }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: approvalQueryKey }),
  });
}
