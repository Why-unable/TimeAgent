import type { ComponentType } from "react";

import type { InteractionType } from "../../api/interactions";
import type { CompletionHarvestProps, MemorySuggestionProps } from "../today/completion-check-in";
import { CompletionHarvest, MemorySuggestionCard } from "../today/completion-check-in";
import type { PlanInteractionProps } from "./interactive-plan-timeline";
import { InteractivePlanTimeline, PriorityRanker } from "./interactive-plan-timeline";

type PropsFor<K extends InteractionType> = K extends "priority_ranking" | "plan_timeline_edit"
  ? PlanInteractionProps
  : K extends "task_completion"
    ? CompletionHarvestProps
    : K extends "memory_suggestion"
      ? MemorySuggestionProps
      : never;

export type InteractionComponentRegistry = {
  [K in InteractionType]: ComponentType<PropsFor<K>>;
};

export const interactionComponentRegistry: InteractionComponentRegistry = {
  priority_ranking: PriorityRanker,
  plan_timeline_edit: InteractivePlanTimeline,
  task_completion: CompletionHarvest,
  memory_suggestion: MemorySuggestionCard,
};
