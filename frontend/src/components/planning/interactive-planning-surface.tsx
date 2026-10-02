import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import type { InteractionArtifact, InteractionType } from "../../api/interactions";
import { ensureInteraction, listPendingInteractions } from "../../api/interactions";
import { getSchedulePlan, type SchedulePlan } from "../../api/planning";
import { formatInUserTimezone, formatTimeInUserTimezone } from "../../utils/datetime";
import { interactionComponentRegistry } from "./interaction-component-registry";

type PlanSummaryItem = {
  kind?: string;
  task_id?: string;
  task_title?: string;
  state?: string;
  start_at?: string;
  end_at?: string;
};

export function InteractivePlanningSurface({
  plan,
  taskTitles,
  timezone,
  onPlanChange,
  onRefreshPlan,
  conversationId,
  agentRunId,
  agentRunActive = false,
}: {
  plan: SchedulePlan;
  taskTitles: Map<string, string>;
  timezone: string;
  onPlanChange?: (plan: SchedulePlan) => void;
  onRefreshPlan?: () => Promise<void>;
  conversationId?: string;
  agentRunId?: string;
  agentRunActive?: boolean;
}) {
  const [activePlan, setActivePlan] = useState(plan);
  const [activeType, setActiveType] = useState<InteractionType | null>(null);
  const [snoozedInteractionId, setSnoozedInteractionId] = useState<string | null>(null);
  const [focusOnOpen, setFocusOnOpen] = useState(false);
  const [focusReturnType, setFocusReturnType] = useState<InteractionType | null>(null);
  const [agentAnnouncement, setAgentAnnouncement] = useState("");
  const selectionRefs = useRef<Partial<Record<InteractionType, HTMLButtonElement | null>>>({
    priority_ranking: null,
    plan_timeline_edit: null,
  });
  const announcedInteractionIds = useRef(new Set<string>());
  const previousRunActive = useRef(agentRunActive);
  const queryClient = useQueryClient();
  const pendingInteractions = useQuery({
    queryKey: ["interactions", plan.id],
    queryFn: () => listPendingInteractions({ plan_id: plan.id }),
    enabled: plan.status === "draft" && Boolean(agentRunId),
    refetchInterval: (query) => agentRunActive && !query.state.data?.some((interaction) =>
      interaction.agent_run_id === agentRunId
      && (interaction.type === "priority_ranking" || interaction.type === "plan_timeline_edit"),
    ) ? 1_000 : false,
    staleTime: 0,
    retry: false,
  });
  const priority = useQuery({
    queryKey: ["interaction", plan.id, "priority_ranking"],
    queryFn: () => ensureInteraction({ type: "priority_ranking", plan_id: plan.id, conversation_id: conversationId, agent_run_id: agentRunId }),
    enabled: plan.status === "draft" && activeType === "priority_ranking",
    staleTime: 30_000,
    retry: false,
  });
  const timeline = useQuery({
    queryKey: ["interaction", plan.id, "plan_timeline_edit"],
    queryFn: () => ensureInteraction({ type: "plan_timeline_edit", plan_id: plan.id, conversation_id: conversationId, agent_run_id: agentRunId }),
    enabled: plan.status === "draft" && activeType === "plan_timeline_edit",
    staleTime: 30_000,
    retry: false,
  });

  useEffect(() => setActivePlan(plan), [plan]);

  useEffect(() => {
    if (previousRunActive.current && !agentRunActive) {
      void queryClient.refetchQueries({ queryKey: ["interactions", plan.id] });
    }
    previousRunActive.current = agentRunActive;
  }, [agentRunActive, plan.id, queryClient]);

  useEffect(() => {
    if (plan.status !== "draft") return;
    void queryClient.invalidateQueries({ queryKey: ["interaction", plan.id] });
    void queryClient.invalidateQueries({ queryKey: ["interactions", plan.id] });
  }, [plan.id, plan.status, plan.version, queryClient]);

  useEffect(() => {
    const agentInteraction = pendingInteractions.data?.find((interaction) =>
      interaction.status === "pending"
      && interaction.agent_run_id === agentRunId
      && (interaction.type === "priority_ranking" || interaction.type === "plan_timeline_edit"),
    );
    if (!agentInteraction || agentInteraction.id === snoozedInteractionId) return;
    queryClient.setQueryData(
      ["interaction", plan.id, agentInteraction.type],
      agentInteraction,
    );
    if (!activeType) {
      setFocusOnOpen(false);
      setActiveType(agentInteraction.type);
      if (!announcedInteractionIds.current.has(agentInteraction.id)) {
        const label = agentInteraction.type === "priority_ranking" ? "调整本次任务顺序" : "调整时间与时长";
        setAgentAnnouncement(`助理已准备好“${label}”交互，现已打开。`);
        announcedInteractionIds.current.add(agentInteraction.id);
      }
    }
  }, [activeType, agentRunId, pendingInteractions.data, plan.id, queryClient, snoozedInteractionId]);

  useEffect(() => {
    if (activeType || !focusReturnType) return;
    selectionRefs.current[focusReturnType]?.focus();
    setFocusReturnType(null);
  }, [activeType, focusReturnType]);

  const updatePlan = (next: SchedulePlan) => {
    setActivePlan(next);
    onPlanChange?.(next);
  };

  const snooze = (interaction: InteractionArtifact) => {
    // Keep the server artifact pending. Reopening this tool, or returning to the
    // draft later, restores the same decision instead of permanently abandoning it.
    setActiveType(null);
    setFocusOnOpen(false);
    setFocusReturnType(interaction.type);
    setSnoozedInteractionId(interaction.id);
    queryClient.setQueryData(["interaction", plan.id, interaction.type], interaction);
  };

  const refreshCurrentPlan = async () => {
    if (onRefreshPlan) {
      await onRefreshPlan();
    } else {
      updatePlan(await getSchedulePlan(plan.id));
    }
    await queryClient.invalidateQueries({ queryKey: ["interaction", plan.id] });
  };

  const PriorityRenderer = interactionComponentRegistry.priority_ranking;
  const TimelineRenderer = interactionComponentRegistry.plan_timeline_edit;
  const activeQuery = activeType === "priority_ranking" ? priority : timeline;
  const interactionPending = activeType !== null && activeQuery.isPending;
  const interactionUnavailable = activeType !== null && activeQuery.isError;
  const summaryItems = (Array.isArray(plan.items) ? plan.items : []) as PlanSummaryItem[];
  return (
    <div className="space-y-3">
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{agentAnnouncement}</p>
      {!activeType && (
        <ol aria-label="草案当前安排" className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
          {summaryItems.filter((item) => item.kind !== "plan_evidence" && item.task_id).map((item, index) => (
            <li key={`${item.task_id}-${index}`} className="flex flex-wrap justify-between gap-2 py-1 text-xs text-slate-300">
              <span>{taskTitles.get(item.task_id ?? "") ?? item.task_title ?? "任务"}</span>
              <span>{item.start_at ? `${formatInUserTimezone(item.start_at, timezone)}–${formatTimeInUserTimezone(item.end_at ?? item.start_at, timezone)}` : "尚未安排"}</span>
            </li>
          ))}
        </ol>
      )}
      {!activeType && plan.status === "draft" && (
        <div className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
          <p className="text-xs text-slate-400">需要调整时，选择一个具体操作；计划顺序和时间安排分别打开。</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button ref={(element) => { selectionRefs.current.priority_ranking = element; }} type="button" aria-pressed={false} onClick={() => { setFocusOnOpen(true); setActiveType("priority_ranking"); }} className="min-h-11 rounded-lg border border-white/15 px-3 text-sm text-slate-200 hover:bg-white/5">调整本次任务顺序</button>
            <button ref={(element) => { selectionRefs.current.plan_timeline_edit = element; }} type="button" aria-pressed={false} onClick={() => { setFocusOnOpen(true); setActiveType("plan_timeline_edit"); }} className="min-h-11 rounded-lg border border-white/15 px-3 text-sm text-slate-200 hover:bg-white/5">调整时间与时长</button>
          </div>
        </div>
      )}
      {activeType && interactionPending && <p role="status" className="rounded-lg border border-white/10 p-3 text-xs text-slate-400">正在恢复这项计划交互…</p>}
      {activeType === "priority_ranking" && priority.isError && (
        <p role="alert" className="rounded-lg border border-amber-300/20 p-3 text-xs text-amber-100">
          无法恢复本次计划的优先顺序交互。<button type="button" className="ml-2 underline" onClick={() => void priority.refetch()}>重试</button>
        </p>
      )}
      {activeType === "plan_timeline_edit" && timeline.isError && (
        <p role="alert" className="rounded-lg border border-amber-300/20 p-3 text-xs text-amber-100">
          无法恢复计划时间线交互。<button type="button" className="ml-2 underline" onClick={() => void timeline.refetch()}>重试</button>
        </p>
      )}
      {activeType === "priority_ranking" && priority.data && <>
        <PriorityRenderer plan={activePlan} interaction={priority.data} taskTitles={taskTitles} timezone={timezone} onPlanChange={updatePlan} onSnooze={snooze} onRefreshPlan={refreshCurrentPlan} focusOnMount={focusOnOpen} />
      </>}
      {activeType === "plan_timeline_edit" && timeline.data && <>
        <TimelineRenderer plan={activePlan} interaction={timeline.data} taskTitles={taskTitles} timezone={timezone} onPlanChange={updatePlan} onSnooze={snooze} onRefreshPlan={refreshCurrentPlan} focusOnMount={focusOnOpen} />
      </>}
      {activeType && !interactionPending && (interactionUnavailable || !activeQuery.data) && <button type="button" onClick={() => { setFocusReturnType(activeType); setActiveType(null); }} className="min-h-11 rounded-lg px-3 text-xs text-slate-400 hover:bg-white/5">返回计划</button>}
    </div>
  );
}
