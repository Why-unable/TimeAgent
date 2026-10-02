import {
  DndContext,
  PointerSensor,
  closestCenter,
  useDraggable,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  useDroppable,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripHorizontal, GripVertical, Lock, MoveDown, MoveUp, Unlock } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { InteractionArtifact } from "../../api/interactions";
import {
  recordInteractionTelemetry,
  submitInteraction,
} from "../../api/interactions";
import { ApiError } from "../../api/client";
import type { SchedulePlan } from "../../api/planning";
import { formatTimeInUserTimezone, toDateTimeLocalValue, toUtcISOString } from "../../utils/datetime";

type PlanItem = {
  kind?: string;
  task_id?: string;
  state?: string;
  start_at?: string;
  end_at?: string;
  locked?: boolean;
  planning_order?: number;
  planned_duration_minutes?: number;
  task_title?: string;
  segment_index?: number;
  segment_count?: number;
};

export type PlanInteractionProps = {
  plan: SchedulePlan;
  interaction: InteractionArtifact | null;
  taskTitles: Map<string, string>;
  timezone: string;
  onPlanChange: (plan: SchedulePlan) => void;
  onSnooze: (interaction: InteractionArtifact) => void;
  onRefreshPlan: () => Promise<void>;
  focusOnMount?: boolean;
};

function createIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() ?? `interaction-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function sendTelemetry(event: Parameters<typeof recordInteractionTelemetry>[0]) {
  void recordInteractionTelemetry(event).catch(() => undefined);
}

function interactionError(error: unknown) {
  if (error instanceof ApiError && error.status === 409) {
    return "计划或交互已被其他操作更新。请刷新计划后再试。";
  }
  return error instanceof Error ? error.message : "暂时无法保存这次计划调整。";
}

function itemList(plan: SchedulePlan) {
  return (Array.isArray(plan.items) ? plan.items : []) as PlanItem[];
}

function planTaskItems(plan: SchedulePlan) {
  return itemList(plan).filter((item) => item.kind !== "plan_evidence" && item.task_id);
}

function reasonLabel(code: string) {
  const labels: Record<string, string> = {
    schedule_conflict: "与现有日程或任务时间冲突",
    work_hours_violation: "超出你的工作时段",
    deadline_violation: "超过任务截止时间",
    max_daily_minutes_violation: "超过每日可安排时长",
    planning_exact_start_violation: "不符合指定的准确开始时间",
    planning_dependency_order_violation: "违反任务依赖顺序",
    plan_item_locked: "该时间块已固定，请先解锁",
    task_version_changed: "任务在计划创建后发生了变化",
    schedule_in_past: "不能把任务安排在过去",
  };
  return labels[code] ?? code.replaceAll("_", " ");
}

export function PriorityRanker({
  plan,
  interaction,
  taskTitles,
  onPlanChange,
  onSnooze,
  onRefreshPlan,
  focusOnMount = false,
}: PlanInteractionProps) {
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [dragCount, setDragCount] = useState(0);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [stalePlan, setStalePlan] = useState(false);
  const [refreshingPlan, setRefreshingPlan] = useState(false);
  const regionRef = useRef<HTMLElement | null>(null);
  const queryClient = useQueryClient();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );
  const orderedItems = useMemo(() => {
    const seen = new Set<string>();
    return planTaskItems(plan)
      .filter((item) => {
        const id = item.task_id;
        if (!id || seen.has(id)) return false;
        seen.add(id);
        return true;
      })
      .map((item, index) => ({ item, index }))
      .sort((a, b) => (a.item.planning_order ?? a.index) - (b.item.planning_order ?? b.index))
      .map(({ item }) => item);
  }, [plan]);
  const ids = orderedItems.map((item) => item.task_id as string);
  const interactionId = interaction?.id;
  const interactionType = interaction?.type;

  const rankingAnnouncements: Announcements = {
    onDragStart: ({ active }) => {
      const index = ids.indexOf(String(active.id));
      const title = taskTitles.get(String(active.id)) ?? "任务";
      return `已选中${title}，当前第 ${index + 1} 项。键盘排序请使用上移或下移按钮。`;
    },
    onDragOver: ({ active, over }) => {
      if (!over) return;
      const title = taskTitles.get(String(active.id)) ?? "任务";
      const index = ids.indexOf(String(over.id));
      return `${title}，第 ${index + 1} 项。`;
    },
    onDragEnd: ({ active, over }) => {
      const title = taskTitles.get(String(active.id)) ?? "任务";
      return over ? `正在保存${title}的本次计划顺序。` : `已取消${title}的排序。`;
    },
    onDragCancel: ({ active }) => `已取消${taskTitles.get(String(active.id)) ?? "任务"}的排序。`,
  };

  useEffect(() => {
    if (interactionId && interactionType) {
      sendTelemetry({ event_type: "interaction_shown", interaction_type: interactionType });
    }
  }, [interactionId, interactionType]);

  useEffect(() => {
    if (focusOnMount) regionRef.current?.focus();
  }, [focusOnMount]);

  const submitOrder = async (orderedTaskIds: string[], dragged: boolean, focusTaskId?: string) => {
    if (!interaction || orderedTaskIds.length < 1) return;
    const started = startedAt ?? Date.now();
    if (!startedAt) {
      setStartedAt(started);
      sendTelemetry({ event_type: "interaction_started", interaction_type: interaction.type });
    }
    setError("");
    setMessage("");
    try {
      const result = await submitInteraction(interaction.id, {
        expected_version: interaction.version,
        action: "reorder",
        values: { ordered_task_ids: orderedTaskIds },
        idempotency_key: createIdempotencyKey(),
      });
      if (!result.accepted || !result.plan) {
        setError(result.detail ?? "计划顺序没有更新。");
        if (result.plan) {
          queryClient.setQueryData(["interaction", plan.id, interaction.type], result.interaction);
          queryClient.setQueryData<InteractionArtifact | undefined>(["interaction", plan.id, "priority_ranking"], (current) => current ? { ...current, plan_version: result.plan?.version ?? current.plan_version } : current);
          queryClient.setQueryData<InteractionArtifact | undefined>(["interaction", plan.id, "plan_timeline_edit"], (current) => current ? { ...current, plan_version: result.plan?.version ?? current.plan_version } : current);
          onPlanChange(result.plan);
        }
        if (dragged) {
          sendTelemetry({ event_type: "invalid_drop", interaction_type: interaction.type, drag_count: dragCount + 1, invalid_drop_count: 1 });
        }
        return;
      }
      queryClient.setQueryData(["interaction", plan.id, interaction.type], result.interaction);
      queryClient.setQueryData<InteractionArtifact | undefined>(["interaction", plan.id, "priority_ranking"], (current) => current ? { ...current, plan_version: result.plan?.version ?? current.plan_version } : current);
      queryClient.setQueryData<InteractionArtifact | undefined>(["interaction", plan.id, "plan_timeline_edit"], (current) => current ? { ...current, plan_version: result.plan?.version ?? current.plan_version } : current);
      onPlanChange(result.plan);
      setMessage("已更新本次计划顺序；任务的永久优先级没有更改。");
      setStartedAt(null);
      window.requestAnimationFrame(() => document.getElementById(`priority-handle-${focusTaskId ?? orderedTaskIds[0]}`)?.focus());
    } catch (caught) {
      setError(interactionError(caught));
      setStalePlan(caught instanceof ApiError && caught.status === 409);
    }
  };

  const onDragEnd = (event: DragEndEvent) => {
    if (!event.over || event.active.id === event.over.id) return;
    const from = ids.indexOf(String(event.active.id));
    const to = ids.indexOf(String(event.over.id));
    if (from < 0 || to < 0) return;
    const next = arrayMove(ids, from, to);
    setDragCount((count) => count + 1);
    void submitOrder(next, true, String(event.active.id));
  };

  const moveByButton = (taskId: string, delta: -1 | 1) => {
    const from = ids.indexOf(taskId);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= ids.length) return;
    void submitOrder(arrayMove(ids, from, to), false, taskId);
  };

  if ((interaction && interaction.status !== "pending") || plan.status !== "draft") return null;

  return (
    <section ref={regionRef} tabIndex={focusOnMount ? -1 : undefined} className="mt-4 rounded-xl border border-white/10 bg-slate-900/70 p-3" aria-label="本次计划优先顺序">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-slate-100">本次计划的任务顺序</h4>
          <p className="mt-1 text-xs text-slate-400">拖动或使用上移、下移按钮。不会修改任务的永久优先级。</p>
        </div>
        {interaction && <button type="button" onClick={() => onSnooze(interaction)} className="min-h-10 rounded-lg px-3 text-xs text-slate-400 hover:bg-white/5">稍后再处理</button>}
      </div>
      {interaction ? (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={onDragEnd}
          accessibility={{
            announcements: rankingAnnouncements,
            screenReaderInstructions: { draggable: "键盘排序请使用每个任务的上移或下移按钮。" },
          }}
        >
          <SortableContext items={ids} strategy={verticalListSortingStrategy}>
            <ol className="mt-3 space-y-2">
              {orderedItems.map((item, index) => {
                const id = item.task_id as string;
                return (
                  <SortablePriorityRow
                    key={id}
                    id={id}
                    title={taskTitles.get(id) ?? item.task_title ?? "任务"}
                    index={index}
                    count={orderedItems.length}
                    onMove={moveByButton}
                  />
                );
              })}
            </ol>
          </SortableContext>
        </DndContext>
      ) : <p role="status" className="mt-3 text-xs text-slate-400">正在恢复可交互顺序…</p>}
      {message && <p role="status" className="mt-3 text-xs text-emerald-200">{message}</p>}
      {error && <div role="alert" className="mt-3 rounded-lg border border-amber-300/20 p-3 text-xs text-amber-100"><p>{error}</p>{stalePlan && <button type="button" disabled={refreshingPlan} onClick={() => { setRefreshingPlan(true); void onRefreshPlan().then(() => { setError(""); setStalePlan(false); }).catch(() => setError("最新计划暂时无法载入，请重试。")).finally(() => setRefreshingPlan(false)); }} className="mt-2 min-h-10 underline disabled:opacity-50">{refreshingPlan ? "正在同步…" : "同步最新计划"}</button>}</div>}
    </section>
  );
}

function SortablePriorityRow({
  id,
  title,
  index,
  count,
  onMove,
}: {
  id: string;
  title: string;
  index: number;
  count: number;
  onMove: (id: string, delta: -1 | 1) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex items-center gap-2 rounded-lg border border-white/10 bg-slate-950/60 p-2 ${isDragging ? "opacity-50" : ""}`}
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        id={`priority-handle-${id}`}
        aria-label={`鼠标或触屏拖动排序：${title}，当前第 ${index + 1} 项；键盘使用上移或下移按钮`}
        tabIndex={-1}
        className="grid min-h-11 min-w-11 place-items-center touch-none rounded-lg text-slate-400 hover:bg-white/5"
      >
        <GripVertical size={18} />
      </button>
      <span className="min-w-0 flex-1 text-sm text-slate-100">{index + 1}. {title}</span>
      <button type="button" aria-label={`上移：${title}`} disabled={index === 0} onClick={() => onMove(id, -1)} className="min-h-11 min-w-11 rounded-lg text-slate-300 hover:bg-white/5 disabled:opacity-30">
        <MoveUp size={16} className="mx-auto" />
      </button>
      <button type="button" aria-label={`下移：${title}`} disabled={index === count - 1} onClick={() => onMove(id, 1)} className="min-h-11 min-w-11 rounded-lg text-slate-300 hover:bg-white/5 disabled:opacity-30">
        <MoveDown size={16} className="mx-auto" />
      </button>
    </li>
  );
}

export function InteractivePlanTimeline({
  plan,
  interaction,
  taskTitles,
  timezone,
  onPlanChange,
  onSnooze,
  onRefreshPlan,
  focusOnMount = false,
}: PlanInteractionProps) {
  const [error, setError] = useState("");
  const [reasonCodes, setReasonCodes] = useState<string[]>([]);
  const [conflicts, setConflicts] = useState<Array<{ kind: string; label: string; start_at: string; end_at: string }>>([]);
  const [candidate, setCandidate] = useState<{ taskId: string; start_at: string; end_at: string } | null>(null);
  const [undoSnapshot, setUndoSnapshot] = useState<{ taskId: string; start_at: string; end_at: string; locked: boolean } | null>(null);
  const [message, setMessage] = useState("");
  const [dragCount, setDragCount] = useState(0);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [stalePlan, setStalePlan] = useState(false);
  const [refreshingPlan, setRefreshingPlan] = useState(false);
  const regionRef = useRef<HTMLElement | null>(null);
  const queryClient = useQueryClient();
  const interactionId = interaction?.id;
  const interactionType = interaction?.type;
  useEffect(() => {
    if (focusOnMount) regionRef.current?.focus();
  }, [focusOnMount]);
  const timelineAnnouncements: Announcements = {
    onDragStart: ({ active }) => {
      const rawId = String(active.id);
      const resizing = rawId.startsWith("resize:");
      const taskId = resizing ? rawId.slice("resize:".length) : rawId;
      const title = taskTitles.get(taskId) ?? "任务";
      return resizing
        ? `已选中${title}的时长调整柄。键盘可使用时长输入框和保存按钮。`
        : `已选中${title}的时间块。键盘可使用开始时间输入框和微调按钮。`;
    },
    onDragOver: ({ active }) => {
      const rawId = String(active.id);
      const resizing = rawId.startsWith("resize:");
      const taskId = resizing ? rawId.slice("resize:".length) : rawId;
      return `${taskTitles.get(taskId) ?? "任务"}，${resizing ? "调整时长" : "调整开始时间"}。`;
    },
    onDragEnd: ({ active, over }) => {
      const rawId = String(active.id);
      const resizing = rawId.startsWith("resize:");
      const taskId = resizing ? rawId.slice("resize:".length) : rawId;
      return over
        ? `正在保存${taskTitles.get(taskId) ?? "任务"}${resizing ? "的预计时长" : "的安排时间"}。`
        : `已取消${taskTitles.get(taskId) ?? "任务"}的调整。`;
    },
    onDragCancel: ({ active }) => {
      const rawId = String(active.id);
      const taskId = rawId.startsWith("resize:") ? rawId.slice("resize:".length) : rawId;
      return `已取消${taskTitles.get(taskId) ?? "任务"}的调整。`;
    },
  };
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );
  const visibleItems = planTaskItems(plan).slice().sort((left, right) => {
    if (!left.start_at) return right.start_at ? 1 : 0;
    if (!right.start_at) return -1;
    return new Date(left.start_at).getTime() - new Date(right.start_at).getTime();
  });
  const countsByTask = new Map<string, number>();
  visibleItems.forEach((item) => countsByTask.set(item.task_id as string, (countsByTask.get(item.task_id as string) ?? 0) + 1));

  useEffect(() => {
    if (interactionId && interactionType) {
      sendTelemetry({ event_type: "interaction_shown", interaction_type: interactionType });
    }
  }, [interactionId, interactionType]);

  const submitEdit = async (
    taskId: string,
    startAt: string,
    endAt: string,
    locked?: boolean,
    isDrag = false,
    isUndo = false,
  ): Promise<boolean> => {
    if (!interaction) return false;
    const started = startedAt ?? Date.now();
    if (!startedAt) {
      setStartedAt(started);
      sendTelemetry({ event_type: "interaction_started", interaction_type: interaction.type });
    }
    setError("");
    setReasonCodes([]);
    setConflicts([]);
    setCandidate(null);
    setMessage("");
    try {
      const result = await submitInteraction(interaction.id, {
        expected_version: interaction.version,
        action: "edit",
        values: {
          items: [{ task_id: taskId, start_at: startAt, end_at: endAt, ...(locked === undefined ? {} : { locked }) }],
        },
        idempotency_key: createIdempotencyKey(),
      });
      if (!result.accepted || !result.plan) {
        setError(result.detail ?? "后端没有接受这次计划调整。");
        setReasonCodes(result.reason_codes);
        setConflicts(result.conflicts);
        setCandidate(result.candidate ? { taskId, ...result.candidate } : null);
        if (result.plan) {
          queryClient.setQueryData(["interaction", plan.id, interaction.type], result.interaction);
          queryClient.setQueryData<InteractionArtifact | undefined>(["interaction", plan.id, "priority_ranking"], (current) => current ? { ...current, plan_version: result.plan?.version ?? current.plan_version } : current);
          queryClient.setQueryData<InteractionArtifact | undefined>(["interaction", plan.id, "plan_timeline_edit"], (current) => current ? { ...current, plan_version: result.plan?.version ?? current.plan_version } : current);
          onPlanChange(result.plan);
        }
        if (isDrag) sendTelemetry({ event_type: "invalid_drop", interaction_type: interaction.type, drag_count: dragCount + 1, invalid_drop_count: 1 });
        return false;
      }
      queryClient.setQueryData(["interaction", plan.id, interaction.type], result.interaction);
      queryClient.setQueryData<InteractionArtifact | undefined>(["interaction", plan.id, "priority_ranking"], (current) => current ? { ...current, plan_version: result.plan?.version ?? current.plan_version } : current);
      queryClient.setQueryData<InteractionArtifact | undefined>(["interaction", plan.id, "plan_timeline_edit"], (current) => current ? { ...current, plan_version: result.plan?.version ?? current.plan_version } : current);
      onPlanChange(result.plan);
      const previous = visibleItems.find((item) => item.task_id === taskId);
      const next = planTaskItems(result.plan).find((item) => item.task_id === taskId);
      const title = taskTitles.get(taskId) ?? "任务";
      setMessage(locked !== undefined
        ? `${title}已${locked ? "固定" : "解除固定"}。计划仍是草案。`
        : `${title}：${previous?.start_at ? `${formatTimeInUserTimezone(previous.start_at, timezone)}–${formatTimeInUserTimezone(previous.end_at ?? previous.start_at, timezone)}` : "未安排"} → ${next?.start_at ? `${formatTimeInUserTimezone(next.start_at, timezone)}–${formatTimeInUserTimezone(next.end_at ?? next.start_at, timezone)}` : "未安排"}。计划仍是草案。`);
      setStartedAt(null);
      if (isUndo) {
        setUndoSnapshot(null);
      } else if (previous?.start_at && previous.end_at) {
        setUndoSnapshot({ taskId, start_at: previous.start_at, end_at: previous.end_at, locked: Boolean(previous.locked) });
      }
      sendTelemetry({ event_type: "plan_edit", interaction_type: interaction.type, plan_edit_count: 1 });
      if (isUndo) sendTelemetry({ event_type: "undo", interaction_type: interaction.type, undo_count: 1 });
      const oldHandle = document.getElementById(`timeline-handle-${taskId}`);
      window.requestAnimationFrame(() => oldHandle?.focus());
      return true;
    } catch (caught) {
      setError(interactionError(caught));
      setStalePlan(caught instanceof ApiError && caught.status === 409);
      return false;
    }
  };

  const onTimelineDragEnd = (event: DragEndEvent) => {
    const dragId = String(event.active.id);
    const resizing = dragId.startsWith("resize:");
    const taskId = resizing ? dragId.slice("resize:".length) : dragId;
    const item = visibleItems.find((candidateItem) => candidateItem.task_id === taskId);
    if (!item?.start_at || !item.end_at || event.delta.y === 0) return;
    const deltaMinutes = Math.round(event.delta.y / 32) * 15;
    if (!deltaMinutes) return;
    const duration = new Date(item.end_at).getTime() - new Date(item.start_at).getTime();
    setDragCount((count) => count + 1);
    if (resizing) {
      const newDuration = Math.max(5 * 60_000, duration + deltaMinutes * 60_000);
      void submitEdit(
        taskId,
        item.start_at,
        new Date(new Date(item.start_at).getTime() + newDuration).toISOString(),
        undefined,
        true,
      );
      return;
    }
    const newStart = new Date(new Date(item.start_at).getTime() + deltaMinutes * 60_000);
    void submitEdit(taskId, newStart.toISOString(), new Date(newStart.getTime() + duration).toISOString(), undefined, true);
  };

  const submitCandidate = () => {
    if (!candidate) return;
    void submitEdit(candidate.taskId, candidate.start_at, candidate.end_at);
  };

  const undoLastEdit = () => {
    if (!undoSnapshot) return;
    void submitEdit(
      undoSnapshot.taskId,
      undoSnapshot.start_at,
      undoSnapshot.end_at,
      undoSnapshot.locked,
      false,
      true,
    );
  };

  return (
    <section ref={regionRef} tabIndex={focusOnMount ? -1 : undefined} className="mt-4 rounded-xl border border-cyan-200/15 bg-slate-900/70 p-3" aria-label="可编辑计划时间线">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 id="plan-timeline-heading" tabIndex={-1} className="text-sm font-semibold text-slate-100">可交互时间线</h4>
          <p className="mt-1 text-xs text-slate-400">拖动任务块上下调整时间（每 32 像素约 15 分钟）；也可用键盘输入或按钮微调。</p>
        </div>
        {interaction && <button type="button" onClick={() => onSnooze(interaction)} className="min-h-10 rounded-lg px-3 text-xs text-slate-400 hover:bg-white/5">稍后再处理</button>}
      </div>
      {interaction?.status === "pending" && plan.status === "draft" ? (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={onTimelineDragEnd}
          accessibility={{
            announcements: timelineAnnouncements,
            screenReaderInstructions: { draggable: "键盘调整请使用开始时间与时长输入框、前后 15 分钟按钮，再激活保存。" },
          }}
        >
          <ol className="mt-3 space-y-3">
            {visibleItems.map((item, index) => {
              const taskId = item.task_id as string;
              const title = taskTitles.get(taskId) ?? item.task_title ?? "任务";
              const movable = item.state === "placed" && Boolean(item.start_at && item.end_at) && countsByTask.get(taskId) === 1;
              return (
                <TimelineTaskCard
                  key={`${taskId}-${item.segment_index ?? index}`}
                  taskId={taskId}
                  item={item}
                  title={title}
                  timezone={timezone}
                  movable={movable}
                  onSubmit={(startAt, endAt, locked) => submitEdit(taskId, startAt, endAt, locked)}
                />
              );
            })}
          </ol>
        </DndContext>
      ) : <p role="status" className="mt-3 text-xs text-slate-400">正在恢复计划交互…</p>}
      {message && <p role="status" className="mt-3 text-xs text-emerald-200">{message}</p>}
      {undoSnapshot && <button type="button" onClick={undoLastEdit} className="mt-3 min-h-11 rounded-lg border border-white/15 px-3 text-xs text-slate-200">撤销上次调整</button>}
      {error && (
        <div role="alert" className="mt-3 rounded-lg border border-amber-300/25 bg-amber-300/5 p-3 text-xs text-amber-100">
          <p>{error}</p>
          {reasonCodes.map((code) => <p key={code} className="mt-1">原因：{reasonLabel(code)}</p>)}
          {conflicts.map((conflict, index) => (
            <p key={`${conflict.kind}-${index}`} className="mt-1">
              {conflict.label}：{formatTimeInUserTimezone(conflict.start_at, timezone)}–{formatTimeInUserTimezone(conflict.end_at, timezone)}
            </p>
          ))}
          {candidate && <button type="button" onClick={submitCandidate} className="mt-3 min-h-11 rounded-lg bg-cyan-200 px-3 font-semibold text-slate-950">使用推荐时间 {formatTimeInUserTimezone(candidate.start_at, timezone)}–{formatTimeInUserTimezone(candidate.end_at, timezone)}</button>}
          {stalePlan && <button type="button" disabled={refreshingPlan} onClick={() => { setRefreshingPlan(true); void onRefreshPlan().then(() => { setError(""); setStalePlan(false); }).catch(() => setError("最新计划暂时无法载入，请重试。")).finally(() => setRefreshingPlan(false)); }} className="mt-3 min-h-10 underline disabled:opacity-50">{refreshingPlan ? "正在同步…" : "同步最新计划"}</button>}
        </div>
      )}
      {plan.status !== "draft" && <p className="mt-3 text-xs text-slate-400">此计划已不再是草案，交互编辑已关闭。</p>}
    </section>
  );
}

function TimelineTaskCard({
  taskId,
  item,
  title,
  timezone,
  movable,
  onSubmit,
}: {
  taskId: string;
  item: PlanItem;
  title: string;
  timezone: string;
  movable: boolean;
  onSubmit: (startAt: string, endAt: string, locked?: boolean) => Promise<boolean>;
}) {
  const start = item.start_at;
  const end = item.end_at;
  const initialDuration = start && end
    ? Math.max(1, Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60_000))
    : 30;
  const [startLocal, setStartLocal] = useState(start ? toDateTimeLocalValue(start, timezone) : "");
  const [duration, setDuration] = useState(initialDuration);
  const [formError, setFormError] = useState("");
  useEffect(() => {
    setStartLocal(start ? toDateTimeLocalValue(start, timezone) : "");
    setDuration(initialDuration);
  }, [initialDuration, start, timezone]);
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: taskId,
    disabled: !movable || item.locked === true,
  });
  const { setNodeRef: setDropTargetNodeRef } = useDroppable({
    id: taskId,
    disabled: !movable,
  });
  const setCardNodeRef = (node: HTMLElement | null) => {
    setNodeRef(node);
    setDropTargetNodeRef(node);
  };
  const {
    attributes: resizeAttributes,
    listeners: resizeListeners,
    setNodeRef: setResizeNodeRef,
  } = useDraggable({
    id: `resize:${taskId}`,
    disabled: !movable || item.locked === true,
  });
  const style = { transform: CSS.Translate.toString(transform) };

  const updateStart = (delta: number) => {
    if (!startLocal) return;
    try {
      const instant = new Date(toUtcISOString(startLocal, timezone));
      instant.setMinutes(instant.getMinutes() + delta);
      setStartLocal(toDateTimeLocalValue(instant, timezone));
      setFormError("");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "开始时间无效");
    }
  };

  const saveTimes = () => {
    if (!startLocal) return;
    try {
      const startAt = toUtcISOString(startLocal, timezone);
      const endAt = new Date(new Date(startAt).getTime() + duration * 60_000).toISOString();
      void onSubmit(startAt, endAt).then((accepted) => {
        if (!accepted && start && end) {
          setStartLocal(toDateTimeLocalValue(start, timezone));
          setDuration(Math.max(1, Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60_000)));
        }
      });
      setFormError("");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "请检查输入的时间");
    }
  };

  return (
    <li
      ref={setCardNodeRef}
      style={style}
      className={`rounded-xl border border-white/10 bg-slate-950/60 p-3 ${isDragging ? "z-10 opacity-60" : ""}`}
    >
      <div className="flex items-start gap-2">
        <button
          id={`timeline-handle-${taskId}`}
          type="button"
          {...attributes}
          {...listeners}
          disabled={!movable || item.locked === true}
          aria-label={`鼠标或触屏拖动调整时间：${title}；键盘使用开始时间和微调按钮`}
          tabIndex={-1}
          title="拖动上下约每 32 像素调整 15 分钟"
          className="grid min-h-11 min-w-11 touch-none place-items-center rounded-lg text-slate-400 hover:bg-white/5 disabled:opacity-30"
        >
          <GripVertical size={18} />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="min-w-0 flex-1 text-sm font-medium text-slate-100">{title}</p>
            {item.locked && <span className="inline-flex items-center gap-1 text-xs text-slate-400"><Lock size={12} />固定</span>}
          </div>
          <p className="mt-1 text-xs text-cyan-200">
            {start ? `${formatTimeInUserTimezone(start, timezone)}–${formatTimeInUserTimezone(end ?? start, timezone)}` : "尚未安排"}
          </p>
        </div>
        <button type="button" disabled={!movable} aria-label={`${item.locked ? "解锁" : "固定"}：${title}`} onClick={() => start && end && onSubmit(start, end, !item.locked)} className="min-h-11 min-w-11 rounded-lg text-slate-300 hover:bg-white/5 disabled:opacity-30">
          {item.locked ? <Unlock size={16} className="mx-auto" /> : <Lock size={16} className="mx-auto" />}
        </button>
        {movable && item.locked !== true && start && end && (
          <button
            ref={setResizeNodeRef}
            type="button"
            {...resizeAttributes}
            {...resizeListeners}
            aria-label={`鼠标或触屏拖动调整时长：${title}；键盘使用时长输入框`}
            tabIndex={-1}
            title="拖动上下约每 32 像素调整 15 分钟；也可用键盘时长输入"
            className="grid min-h-11 min-w-11 touch-none place-items-center rounded-lg text-slate-400 hover:bg-white/5"
          >
            <GripHorizontal size={18} />
          </button>
        )}
      </div>
      {movable && start && end && item.locked !== true && (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_120px_auto] sm:items-end">
          <label className="text-xs text-slate-400">
            开始时间（{timezone}）
            <input type="datetime-local" value={startLocal} onChange={(event) => setStartLocal(event.target.value)} className="mt-1 min-h-11 w-full rounded-lg border border-white/15 bg-slate-900 px-2 text-sm text-slate-100" />
          </label>
          <label className="text-xs text-slate-400">
            时长（分钟）
            <input type="number" min={5} max={720} step={5} value={duration} onChange={(event) => setDuration(Math.min(720, Math.max(5, Number(event.target.value) || 5)))} className="mt-1 min-h-11 w-full rounded-lg border border-white/15 bg-slate-900 px-2 text-sm text-slate-100" />
          </label>
          <div className="flex gap-2">
            <button type="button" onClick={() => updateStart(-15)} aria-label={`提前 15 分钟：${title}`} className="min-h-11 rounded-lg border border-white/15 px-3 text-xs text-slate-200">−15 分</button>
            <button type="button" onClick={() => updateStart(15)} aria-label={`推后 15 分钟：${title}`} className="min-h-11 rounded-lg border border-white/15 px-3 text-xs text-slate-200">+15 分</button>
            <button type="button" onClick={saveTimes} className="min-h-11 rounded-lg bg-cyan-200 px-3 text-xs font-semibold text-slate-950">保存</button>
          </div>
        </div>
      )}
      {movable && item.locked === true && <p className="mt-2 text-xs text-slate-500">该时间块已固定；解锁后可调整时间。</p>}
      {!movable && <p className="mt-2 text-xs text-slate-500">分段任务或未安排任务暂不支持直接拖动。</p>}
      {formError && <p role="alert" className="mt-2 text-xs text-amber-200">{formError}</p>}
    </li>
  );
}
