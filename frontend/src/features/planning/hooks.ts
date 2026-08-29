import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  abandonSchedulePlan,
  applyLocalReplan,
  applySchedulePlan,
  compareSchedulePlans,
  createSchedulePlan,
  detectScheduleDisruptions,
  editSchedulePlan,
  getFreeTimeRecommendations,
  listAutomationPolicies,
  previewLocalReplan,
  regenerateSchedulePlan,
  revertScheduleChangeBatch,
  saveAutomationPolicy,
  updateAutomationPolicy,
  validateSchedulePlan,
} from "../../api/planning";
import type {
  AutomationPolicyWrite,
  LocalReplanApplyRequest,
  LocalReplanPreviewRequest,
  SchedulePlanApply,
  SchedulePlanCreate,
  SchedulePlanCompare,
  SchedulePlanEdit,
  SchedulePlanRegenerate,
  SchedulePlanValidation,
} from "../../api/planning";

export function useFreeTimeRecommendations(input: {
  range_start: string;
  range_end: string;
  duration_minutes: number;
  max_results?: number;
}, enabled: boolean) {
  return useQuery({
    queryKey: ["planning", "free-time-recommendations", input],
    queryFn: () => getFreeTimeRecommendations(input),
    enabled,
    retry: false,
  });
}

export function useCreateSchedulePlan() {
  return useMutation({ mutationFn: (input: SchedulePlanCreate) => createSchedulePlan(input) });
}

export function useCompareSchedulePlans() {
  return useMutation({ mutationFn: (input: SchedulePlanCompare) => compareSchedulePlans(input) });
}

export function useRegenerateSchedulePlan() {
  return useMutation({
    mutationFn: ({ planId, input }: { planId: string; input: SchedulePlanRegenerate }) =>
      regenerateSchedulePlan(planId, input),
  });
}

export function useEditSchedulePlan() {
  return useMutation({
    mutationFn: ({ planId, input }: { planId: string; input: SchedulePlanEdit }) =>
      editSchedulePlan(planId, input),
  });
}

export function useValidateSchedulePlan() {
  return useMutation({
    mutationFn: ({ planId, input }: { planId: string; input: SchedulePlanValidation }) =>
      validateSchedulePlan(planId, input),
  });
}

export function useAbandonSchedulePlan() {
  return useMutation({
    mutationFn: ({ planId, input }: { planId: string; input: SchedulePlanApply }) =>
      abandonSchedulePlan(planId, input),
  });
}

export function useApplySchedulePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, input }: { planId: string; input: SchedulePlanApply }) =>
      applySchedulePlan(planId, input),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["tasks"] }),
        queryClient.invalidateQueries({ queryKey: ["events"] }),
        queryClient.invalidateQueries({ queryKey: ["today"] }),
      ]);
    },
  });
}

export function useAutomationPolicies() {
  return useQuery({
    queryKey: ["planning", "automation-policies"],
    queryFn: listAutomationPolicies,
    retry: false,
  });
}

export function useSaveAutomationPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: AutomationPolicyWrite) => saveAutomationPolicy(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["planning", "automation-policies"] }),
  });
}

export function useUpdateAutomationPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ policyId, input }: {
      policyId: string;
      input: Partial<AutomationPolicyWrite>;
    }) => updateAutomationPolicy(policyId, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["planning", "automation-policies"] }),
  });
}

export function useDetectScheduleDisruptions() {
  return useMutation({ mutationFn: detectScheduleDisruptions });
}

export function usePreviewLocalReplan() {
  return useMutation({ mutationFn: (input: LocalReplanPreviewRequest) => previewLocalReplan(input) });
}

export function useApplyLocalReplan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: LocalReplanApplyRequest) => applyLocalReplan(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useRevertScheduleChangeBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: revertScheduleChangeBatch,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks"] }),
  });
}
