import { Check, ChevronLeft, ChevronRight, Clock3, Pencil, ShieldAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { ActionProposal, ProposalDecisionResponse } from "../../api/action-proposals";
import { useEvents } from "../../features/events/hooks";
import { useTasks } from "../../features/tasks/hooks";
import { formatInUserTimezone, formatTimeInUserTimezone, getLocalDateTimeProblem, localDateTimeProblemMessage, toDateTimeLocalValue, toUtcISOString } from "../../utils/datetime";

const statusLabels = {
  awaiting_approval: "等待审批",
  approved: "已批准，等待执行",
  rejected: "已拒绝",
  executing: "正在执行",
  executed: "已执行",
  failed: "执行失败",
  expired: "已过期",
} as const;

const actionLabels: Record<string, string> = {
  mutate_events: "调整多项日程",
  create_task_batch: "创建多项任务",
  create_recurring_event: "创建重复日程",
  create_event: "创建日程",
  create_event_batch: "创建多项日程",
  update_event: "修改日程",
  cancel_event: "取消日程",
  apply_schedule_plan: "应用任务计划",
  apply_local_replan: "调整受影响的任务安排",
  change_task_batch_state: "更新多项任务状态",
  reschedule_task: "调整任务时间",
  update_reminder: "修改提醒",
  set_reminder_target: "更改提醒关联对象",
  cancel_reminder: "取消提醒",
  cancel_task: "取消任务",
  remember_time_preference: "保存时间偏好",
  update_time_preference: "修改时间偏好",
  forget_time_preference: "删除时间偏好",
};

const actionSummaryFallbacks: Record<string, string> = {
  mutate_events: "将批量处理日程变更。",
  create_task_batch: "将创建多项任务。",
  create_recurring_event: "将创建重复日程。",
  create_event: "将创建一项日程。",
  create_event_batch: "将创建多项日程。",
  update_event: "将修改一项已有日程。",
  cancel_event: "将取消一项已有日程。",
  apply_schedule_plan: "将应用已保存的任务计划。",
  apply_local_replan: "将尝试调整所选任务的时间。",
  change_task_batch_state: "将更新多项任务的状态。",
  reschedule_task: "将调整一项任务的计划时间。",
  update_reminder: "将修改一项提醒。",
  set_reminder_target: "将更改提醒关联的对象。",
  cancel_reminder: "将取消一项提醒。",
  cancel_task: "将取消一项任务并保留记录。",
  remember_time_preference: "将保存一项时间偏好。",
  update_time_preference: "将修改一项时间偏好。",
  forget_time_preference: "将删除一项时间偏好。",
};

const mutationActionLabels: Record<string, string> = {
  create: "新增",
  update: "调整",
  cancel: "取消",
  link_task: "关联任务",
};

const recurringFrequencyLabels: Record<string, string> = {
  daily: "每天",
  weekly: "每周",
  monthly: "每月",
};

interface ApprovalCardProps {
  proposal: ActionProposal;
  timezone?: string;
  busy?: boolean;
  onDecision: (
    decision: "approve" | "edit" | "reject",
    options?: { actionPayload?: Record<string, unknown>; reason?: string },
  ) => Promise<ProposalDecisionResponse | void>;
}

interface RecurringOccurrencePreview {
  index: number;
  start_at: string;
  end_at: string;
  conflicts: unknown[];
}

interface ConflictDisplayItem {
  title: string;
  start_at?: string;
  end_at?: string;
  overlap_start_at?: string;
  overlap_end_at?: string;
}

interface ActionReviewItem {
  title: string;
  detail?: string;
  time_label?: string;
  proposed_time_label?: string;
  start_at?: string;
  end_at?: string;
  due_at?: string;
  proposed_start_at?: string;
  proposed_end_at?: string;
}

function actionReviewItems(value: unknown): ActionReviewItem[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const review = item as Record<string, unknown>;
    if (typeof review.title !== "string" || !review.title.trim()) return [];
    return [{
      title: review.title.trim(),
      ...(typeof review.detail === "string" ? { detail: review.detail } : {}),
      ...(typeof review.time_label === "string" ? { time_label: review.time_label } : {}),
      ...(typeof review.proposed_time_label === "string" ? { proposed_time_label: review.proposed_time_label } : {}),
      ...(typeof review.start_at === "string" ? { start_at: review.start_at } : {}),
      ...(typeof review.end_at === "string" ? { end_at: review.end_at } : {}),
      ...(typeof review.due_at === "string" ? { due_at: review.due_at } : {}),
      ...(typeof review.proposed_start_at === "string" ? { proposed_start_at: review.proposed_start_at } : {}),
      ...(typeof review.proposed_end_at === "string" ? { proposed_end_at: review.proposed_end_at } : {}),
    }];
  });
}

function ActionReviewPreview({ items, timezone }: { items: ActionReviewItem[]; timezone: string }) {
  if (!items.length) return null;
  const visibleItems = items.slice(0, 3);
  const remainingItems = items.slice(3);
  const renderItems = (rows: ActionReviewItem[], offset = 0) => rows.map((item, index) => (
    <li key={`${item.title}-${offset + index}`} className="approval-preview-item py-3 text-sm text-slate-800 lg:rounded-lg lg:border lg:border-white/10 lg:px-3 lg:py-2 lg:text-slate-200">
      <p className="font-medium">{item.title}</p>
      {item.detail && <p className="mt-1 text-slate-300">{item.detail}</p>}
      {item.start_at && (
        <p className="mt-1 text-xs text-slate-300">
          {item.time_label ?? "当前安排"}：{formatInUserTimezone(item.start_at, timezone)}
          {item.end_at ? ` – ${formatTimeInUserTimezone(item.end_at, timezone)}` : ""}
        </p>
      )}
      {item.due_at && <p className="mt-1 text-xs text-slate-300">截止：{formatInUserTimezone(item.due_at, timezone)}</p>}
      {item.proposed_start_at && (
        <p className="mt-1 text-xs font-medium text-cyan-100">
          {item.proposed_time_label ?? "调整为"}：{formatInUserTimezone(item.proposed_start_at, timezone)}
          {item.proposed_end_at ? ` – ${formatTimeInUserTimezone(item.proposed_end_at, timezone)}` : ""}
        </p>
      )}
    </li>
  ));
  return (
    <div className="mt-3">
      <ul className="divide-y divide-slate-200 lg:space-y-2 lg:divide-y-0">{renderItems(visibleItems)}</ul>
      {remainingItems.length > 0 && <details className="border-t border-slate-200 lg:rounded-lg lg:border lg:border-white/10 lg:px-3">
        <summary className="flex min-h-11 cursor-pointer items-center text-sm font-medium text-cyan-100">查看其余 {remainingItems.length} 项</summary>
        <ul className="divide-y divide-slate-200 pb-3 lg:space-y-2 lg:divide-y-0">{renderItems(remainingItems, visibleItems.length)}</ul>
      </details>}
    </div>
  );
}

function conflictDisplayItems(value: unknown[]): ConflictDisplayItem[] {
  return value.flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const conflict = item as Record<string, unknown>;
    const title = typeof conflict.title === "string" && conflict.title.trim()
      ? conflict.title.trim()
      : "已有日程";
    return [{
      title,
      ...(typeof conflict.start_at === "string" ? { start_at: conflict.start_at } : {}),
      ...(typeof conflict.end_at === "string" ? { end_at: conflict.end_at } : {}),
      ...(typeof conflict.overlap_start_at === "string" ? { overlap_start_at: conflict.overlap_start_at } : {}),
      ...(typeof conflict.overlap_end_at === "string" ? { overlap_end_at: conflict.overlap_end_at } : {}),
    }];
  });
}

function conflictTimeLabel(conflict: ConflictDisplayItem, timezone: string): string {
  if (!conflict.start_at || !conflict.end_at) return "时间信息暂不可用";
  try {
    return `${formatInUserTimezone(conflict.start_at, timezone)} – ${formatTimeInUserTimezone(conflict.end_at, timezone)}`;
  } catch {
    return "时间信息暂不可用";
  }
}

function conflictOverlapLabel(conflict: ConflictDisplayItem, timezone: string): string | null {
  if (!conflict.overlap_start_at || !conflict.overlap_end_at) return null;
  try {
    return `与你的提议重叠：${formatInUserTimezone(conflict.overlap_start_at, timezone)} – ${formatTimeInUserTimezone(conflict.overlap_end_at, timezone)}`;
  } catch {
    return null;
  }
}

function ConflictDetails({ conflicts, timezone }: { conflicts: ConflictDisplayItem[]; timezone: string }) {
  if (!conflicts.length) return null;
  const visibleConflicts = conflicts.slice(0, 3);
  const remainingConflicts = conflicts.slice(3);
  const rows = (items: ConflictDisplayItem[], offset = 0) => (
    <ul className="mt-2 space-y-2">
      {items.map((conflict, index) => {
        const overlapLabel = conflictOverlapLabel(conflict, timezone);
        return (
          <li key={`${conflict.title}-${conflict.start_at ?? ""}-${conflict.end_at ?? ""}-${offset + index}`} className="rounded-lg bg-red-100/70 px-3 py-2">
            <p className="font-medium text-red-950">{conflict.title}</p>
            <p className="mt-1 text-sm text-red-800">已占用：{conflictTimeLabel(conflict, timezone)}</p>
            {overlapLabel && <p className="mt-1 text-sm font-semibold text-red-900">{overlapLabel}</p>}
          </li>
        );
      })}
    </ul>
  );
  return (
    <div role="group" aria-label="冲突日程详情" className="mt-2">
      {rows(visibleConflicts)}
      {remainingConflicts.length > 0 && (
        <details className="mt-2">
            <summary className="min-h-11 cursor-pointer text-xs text-red-800 underline decoration-red-700/40 underline-offset-2">
            查看其余 {remainingConflicts.length} 个冲突
          </summary>
          {rows(remainingConflicts, visibleConflicts.length)}
        </details>
      )}
    </div>
  );
}

function recurringOccurrencePreviews(value: unknown): RecurringOccurrencePreview[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const preview = item as Record<string, unknown>;
    if (
      typeof preview.index !== "number" ||
      typeof preview.start_at !== "string" ||
      typeof preview.end_at !== "string"
    ) return [];
    return [{
      index: preview.index,
      start_at: preview.start_at,
      end_at: preview.end_at,
      conflicts: Array.isArray(preview.conflicts) ? preview.conflicts : [],
    }];
  });
}

function toLocalInput(value: unknown, timezone: string): string {
  if (typeof value !== "string") return "";
  try { return toDateTimeLocalValue(value, timezone); } catch { return ""; }
}

function resolvedReviewPayload(proposal: ActionProposal): Record<string, unknown> {
  const payload = { ...proposal.action_payload };
  if (proposal.action_type === "update_event") {
    const currentItem = actionReviewItems(proposal.display_context.review_items)[0];
    return {
      ...payload,
      ...(typeof proposal.display_context.current_version === "number"
        ? { expected_version: proposal.display_context.current_version }
        : {}),
      ...(typeof payload.title === "string" ? {} : { title: currentItem?.title ?? "" }),
      ...(typeof payload.start_at === "string" ? {} : { start_at: currentItem?.proposed_start_at }),
      ...(typeof payload.end_at === "string" ? {} : { end_at: currentItem?.proposed_end_at }),
    };
  }
  if (proposal.action_type === "mutate_events") {
    const resolved = proposal.display_context.resolved_operations;
    if (Array.isArray(resolved) && resolved.length > 0) {
      const displayOnlyFields = new Set([
        "display_title",
        "existing_start_at",
        "existing_end_at",
        "display_task_title",
        "current_version",
        "version_stale",
      ]);
      const operations = resolved.flatMap((item) => {
        if (!item || typeof item !== "object" || Array.isArray(item)) return [];
        const operation = item as Record<string, unknown>;
        const cleanOperation = Object.fromEntries(
          Object.entries(operation).filter(([key]) => !displayOnlyFields.has(key)),
        );
        if (
          operation.action === "update"
          && (!operation.time || typeof operation.time !== "object")
          && typeof operation.existing_start_at === "string"
          && typeof operation.existing_end_at === "string"
        ) {
          cleanOperation.editor_existing_time = {
            start_at: operation.existing_start_at,
            end_at: operation.existing_end_at,
          };
        }
        if (
          ["create", "update"].includes(String(operation.action))
          && typeof cleanOperation.title !== "string"
          && typeof operation.display_title === "string"
        ) {
          cleanOperation.title = operation.display_title;
        }
        return [cleanOperation];
      });
      return { ...payload, operations };
    }
  }
  if (proposal.action_type === "create_recurring_event") {
    const occurrences = recurringOccurrencePreviews(proposal.display_context.occurrences);
    if (occurrences.length > 0) {
      return {
        ...payload,
        time: {
          kind: "absolute",
          start_at: occurrences[0].start_at,
          end_at: occurrences[0].end_at,
        },
      };
    }
  }
  return payload;
}

function timeRangeError(start: unknown, end: unknown): string | null {
  if (typeof start !== "string" || typeof end !== "string") {
    return "请填写有效的开始和结束时间。";
  }
  const startTime = Date.parse(start);
  const endTime = Date.parse(end);
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) {
    return "请填写有效的开始和结束时间。";
  }
  return startTime < endTime ? null : "结束时间必须晚于开始时间。";
}

function editedPayloadTimeError(actionType: string, payload: Record<string, unknown>): string | null {
  if (actionType === "create_event" || actionType === "update_event") {
    return timeRangeError(payload.start_at, payload.end_at);
  }
  if (actionType === "create_recurring_event") {
    const time = payload.time && typeof payload.time === "object"
      ? payload.time as Record<string, unknown>
      : {};
    return timeRangeError(time.start_at, time.end_at);
  }
  if (actionType === "mutate_events") {
    const operations = Array.isArray(payload.operations) ? payload.operations : [];
    for (const item of operations) {
      if (!item || typeof item !== "object" || Array.isArray(item)) continue;
      const operation = item as Record<string, unknown>;
      const action = String(operation.action ?? "");
      if (action === "cancel" || action === "link_task") continue;
      const time = operation.time && typeof operation.time === "object"
        ? operation.time as Record<string, unknown>
        : undefined;
      if (!time) {
        if (action === "create") return "请为新增日程填写开始和结束时间。";
        continue;
      }
      const error = timeRangeError(time.start_at, time.end_at);
      if (error) return error;
    }
  }
  return null;
}

function PayloadSummary({ actionType, payload, timezone }: { actionType: string; payload: Record<string, unknown>; timezone: string }) {
  const operations = Array.isArray(payload.operations) ? payload.operations : [];
  const time = payload.time && typeof payload.time === "object"
    ? payload.time as Record<string, unknown>
    : payload;
  if (actionType === "mutate_events") {
    return (
      <div className="space-y-2">
        {operations.map((item, index) => {
          const operation = item as Record<string, unknown>;
          const operationTime = operation.time && typeof operation.time === "object" ? operation.time as Record<string, unknown> : {};
          const action = String(operation.action ?? "update");
          const actionLabel = mutationActionLabels[action] ?? "调整";
          const title = operation.display_title ?? operation.title ?? "已有日程";
          return <div key={index} className="border-b border-slate-200 py-3 text-sm text-slate-800 last:border-b-0 lg:rounded-lg lg:border lg:border-slate-200 lg:bg-slate-50 lg:px-3 lg:py-2"><p>{`${index + 1}. ${actionLabel}：${String(title)}`}</p>{typeof operationTime.start_at === "string" && <p className="mt-1 text-xs text-slate-600">{formatInUserTimezone(operationTime.start_at, timezone)}{typeof operationTime.end_at === "string" ? ` – ${formatTimeInUserTimezone(operationTime.end_at, timezone)}` : ""}</p>}</div>;
        })}
      </div>
    );
  }
  return (
    <div className="grid gap-2 text-sm text-slate-200 sm:grid-cols-2">
      <p><span className="text-slate-700">标题：</span>{String(payload.title ?? "未命名日程")}</p>
      {typeof time.start_at === "string" && <p><span className="text-slate-700">开始：</span>{formatInUserTimezone(time.start_at, timezone)}</p>}
      {typeof time.end_at === "string" && <p><span className="text-slate-700">结束：</span>{formatInUserTimezone(time.end_at, timezone)}</p>}
      {actionType === "create_recurring_event" && <p><span className="text-slate-700">重复：</span>{recurringFrequencyLabels[String(payload.frequency ?? "daily")] ?? "按设定频率"}，共 {String(payload.occurrence_count ?? 1)} 次</p>}
    </div>
  );
}

function ReminderTargetEditor({
  payload,
  onChange,
  onReadinessChange,
}: {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  onReadinessChange: (ready: boolean) => void;
}) {
  const tasksQuery = useTasks();
  const eventsQuery = useEvents({ statuses: ["confirmed"] });
  const targetType = String(payload.target_type ?? "custom");
  const targetId = typeof payload.target_id === "string" ? payload.target_id : "";
  const value = targetType === "custom" ? "custom" : `${targetType}:${targetId}`;
  const tasks = (tasksQuery.data ?? []).filter((task) => (
    typeof task.status === "string" && ["pending", "in_progress"].includes(task.status)
  ));
  const events = eventsQuery.data ?? [];
  const loading = tasksQuery.isPending || eventsQuery.isPending;
  const failed = tasksQuery.isError || eventsQuery.isError;
  const currentTargetListed = targetType === "task"
    ? tasks.some((task) => task.id === targetId)
    : targetType === "calendar_event"
      ? events.some((event) => event.id === targetId)
      : targetType === "custom";
  const retainCurrentTargetOption = targetType !== "custom" && !currentTargetListed && Boolean(targetId);
  const currentTargetUnavailable = !loading && !failed && retainCurrentTargetOption;
  const inputClass = "mt-1 min-h-11 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-300/50";

  useEffect(() => {
    onReadinessChange(!loading && !failed);
  }, [failed, loading, onReadinessChange]);

  return (
    <label className="block text-xs text-slate-400">
      提醒关联对象
      <select
        aria-label="提醒关联对象"
        className={inputClass}
        disabled={loading || failed}
        value={value}
        onChange={(event) => {
          const selected = event.target.value;
          if (selected === "custom") {
            onChange({ ...payload, target_type: "custom", target_id: null });
            return;
          }
          const [nextType, ...idParts] = selected.split(":");
          onChange({ ...payload, target_type: nextType, target_id: idParts.join(":") });
        }}
      >
        <option value="custom">独立提醒</option>
        {retainCurrentTargetOption && (
          <option value={value}>
            {loading ? "当前关联对象（正在核对）" : failed ? "当前关联对象（未能核对）" : "当前关联对象（不在可选列表中）"}
          </option>
        )}
        {tasks.map((task) => <option key={task.id} value={`task:${task.id}`}>任务：{task.title}</option>)}
        {events.map((event) => <option key={event.id} value={`calendar_event:${event.id}`}>日程：{event.title}</option>)}
      </select>
      {loading && <span className="mt-1 block text-slate-300">正在加载可关联的任务和日程…</span>}
      {failed && <span role="alert" className="mt-1 block text-red-800">暂时无法读取任务和日程，请稍后重试。</span>}
      {currentTargetUnavailable && <span role="status" className="mt-1 block text-amber-200">当前关联对象不在可选列表中。你可以保留它，或改选列表中的对象。</span>}
    </label>
  );
}

function ApprovalEditor({
  actionType,
  payload,
  timezone,
  onChange,
  onTimeError,
  onTargetEditorReady,
}: {
  actionType: string;
  payload: Record<string, unknown>;
  timezone: string;
  onChange: (next: Record<string, unknown>) => void;
  onTimeError: (message: string) => void;
  onTargetEditorReady: (ready: boolean) => void;
}) {
  const setField = (field: string, value: unknown) => onChange({ ...payload, [field]: value });
  const inputClass = "mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-300/50";
  if (actionType === "create_task_batch") {
    const tasks = Array.isArray(payload.tasks)
      ? payload.tasks.filter((task): task is Record<string, unknown> => Boolean(task) && typeof task === "object" && !Array.isArray(task))
      : [];
    const setTask = (index: number, field: string, value: unknown) => {
      setField("tasks", tasks.map((task, current) => current === index ? { ...task, [field]: value } : task));
    };
    const setTaskTime = (index: number, field: "due_at" | "planned_start_at" | "planned_end_at", value: string) => {
      const problem = value ? getLocalDateTimeProblem(value, timezone) : undefined;
      if (problem) {
        onTimeError(localDateTimeProblemMessage(problem, timezone));
        return;
      }
      const task = tasks[index];
      const nextTask = { ...task };
      if (value) nextTask[field] = toUtcISOString(value, timezone);
      else delete nextTask[field];
      setField("tasks", tasks.map((item, current) => current === index ? nextTask : item));
      onTimeError("");
    };
    return (
      <div className="space-y-3">
        {tasks.map((task, index) => (
          <fieldset key={index} className="grid gap-3 border-t border-slate-200 py-3 first:border-t-0 sm:grid-cols-2">
            <legend className="px-1 text-xs font-medium text-cyan-200">第 {index + 1} 项任务</legend>
            <label className="sm:col-span-2 text-xs text-slate-400">任务名称<input value={String(task.title ?? "")} onChange={(event) => setTask(index, "title", event.target.value)} className={inputClass} /></label>
            <label className="sm:col-span-2 text-xs text-slate-400">任务说明<textarea value={String(task.description ?? "")} onChange={(event) => setTask(index, "description", event.target.value)} className={`${inputClass} min-h-20`} /></label>
            <label className="text-xs text-slate-400">优先级<select value={String(task.priority ?? "medium")} onChange={(event) => setTask(index, "priority", event.target.value)} className={inputClass}><option value="low">低</option><option value="medium">普通</option><option value="high">高</option><option value="urgent">紧急</option></select></label>
            <label className="text-xs text-slate-400">预计用时（分钟）<input type="number" min="0" value={String(task.estimated_minutes ?? "")} onChange={(event) => setTask(index, "estimated_minutes", event.target.value ? Number(event.target.value) : null)} className={inputClass} /></label>
            <label className="text-xs text-slate-400">项目<input value={String(task.project ?? "")} onChange={(event) => setTask(index, "project", event.target.value)} className={inputClass} /></label>
            <label className="text-xs text-slate-400">标签（逗号分隔）<input value={Array.isArray(task.tags) ? task.tags.join(", ") : ""} onChange={(event) => setTask(index, "tags", event.target.value.split(",").map((tag) => tag.trim()).filter(Boolean))} className={inputClass} /></label>
            <label className="text-xs text-slate-400">截止时间（{timezone}）<input type="datetime-local" value={toLocalInput(task.due_at, timezone)} onChange={(event) => setTaskTime(index, "due_at", event.target.value)} className={inputClass} /></label>
            <label className="text-xs text-slate-400">计划开始（{timezone}）<input type="datetime-local" value={toLocalInput(task.planned_start_at, timezone)} onChange={(event) => setTaskTime(index, "planned_start_at", event.target.value)} className={inputClass} /></label>
            <label className="text-xs text-slate-400">计划结束（{timezone}）<input type="datetime-local" value={toLocalInput(task.planned_end_at, timezone)} onChange={(event) => setTaskTime(index, "planned_end_at", event.target.value)} className={inputClass} /></label>
          </fieldset>
        ))}
      </div>
    );
  }
  if (actionType === "mutate_events") {
    const operations = Array.isArray(payload.operations) ? payload.operations : [];
    const setOperation = (index: number, field: string, value: unknown) => {
      const next = operations.map((item, current) => current === index
        ? { ...(item as Record<string, unknown>), [field]: value }
        : item);
      setField("operations", next);
    };
    const setOperationTime = (index: number, field: "start_at" | "end_at", value: string) => {
      const problem = value ? getLocalDateTimeProblem(value, timezone) : undefined;
      if (problem) {
        onTimeError(localDateTimeProblemMessage(problem, timezone));
        return;
      }
      const operation = operations[index] as Record<string, unknown>;
      const time = operation.time && typeof operation.time === "object"
        ? operation.time as Record<string, unknown>
        : operation.editor_existing_time && typeof operation.editor_existing_time === "object"
          ? operation.editor_existing_time as Record<string, unknown>
          : {};
      setOperation(index, "time", { ...time, kind: "absolute", [field]: value ? toUtcISOString(value, timezone) : value });
      onTimeError("");
    };
    return (
      <div className="space-y-3">
        {operations.map((item, index) => {
          const operation = item as Record<string, unknown>;
          const action = String(operation.action ?? "update");
          const time = operation.time && typeof operation.time === "object"
            ? operation.time as Record<string, unknown>
            : operation.editor_existing_time && typeof operation.editor_existing_time === "object"
              ? operation.editor_existing_time as Record<string, unknown>
              : {};
          return (
            <fieldset key={index} className="border-t border-slate-200 py-3 first:border-t-0">
              <legend className="px-1 text-xs font-medium text-cyan-200">第 {index + 1} 项：{mutationActionLabels[action] ?? "调整"}</legend>
              {action !== "cancel" && <label className="block text-xs text-slate-400">日程标题<input value={String(operation.title ?? "")} onChange={(event) => setOperation(index, "title", event.target.value)} className={inputClass} /></label>}
              {action !== "cancel" && <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <label className="text-xs text-slate-400">开始时间（{timezone}）<input type="datetime-local" value={toLocalInput(time.start_at, timezone)} onChange={(event) => setOperationTime(index, "start_at", event.target.value)} className={inputClass} /></label>
                <label className="text-xs text-slate-400">结束时间（{timezone}）<input type="datetime-local" value={toLocalInput(time.end_at, timezone)} onChange={(event) => setOperationTime(index, "end_at", event.target.value)} className={inputClass} /></label>
              </div>}
            </fieldset>
          );
        })}
      </div>
    );
  }
  if (actionType === "update_reminder") {
    const setTriggerTime = (value: string) => {
      if (!value) {
        onTimeError("请选择提醒时间。");
        return;
      }
      const problem = value ? getLocalDateTimeProblem(value, timezone) : undefined;
      if (problem) {
        onTimeError(localDateTimeProblemMessage(problem, timezone));
        return;
      }
      onChange({
        ...payload,
        trigger_at: toUtcISOString(value, timezone),
        timezone,
      });
      onTimeError("");
    };
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="sm:col-span-2 text-xs text-slate-400">提醒名称<input value={String(payload.title ?? "")} onChange={(event) => setField("title", event.target.value)} className={inputClass} /></label>
        <label className="text-xs text-slate-400">提醒时间（{timezone}）<input type="datetime-local" value={toLocalInput(payload.trigger_at, timezone)} onChange={(event) => setTriggerTime(event.target.value)} className={inputClass} /></label>
        <label className="text-xs text-slate-400">通知方式<select value={String(payload.channel ?? "console")} onChange={(event) => setField("channel", event.target.value)} className={inputClass}><option value="console">站内</option><option value="email">邮件</option><option value="telegram">Telegram</option><option value="browser">浏览器</option></select></label>
      </div>
    );
  }
  if (actionType === "set_reminder_target") {
    return <ReminderTargetEditor payload={payload} onChange={onChange} onReadinessChange={onTargetEditorReady} />;
  }
  const time = payload.time && typeof payload.time === "object"
    ? payload.time as Record<string, unknown>
    : payload;
  const setTime = (field: "start_at" | "end_at", value: string) => {
    const problem = value ? getLocalDateTimeProblem(value, timezone) : undefined;
    if (problem) {
      onTimeError(localDateTimeProblemMessage(problem, timezone));
      return;
    }
    const utcValue = value ? toUtcISOString(value, timezone) : value;
    if (payload.time && typeof payload.time === "object") {
      setField("time", { ...time, kind: "absolute", [field]: utcValue });
    } else {
      setField(field, utcValue);
    }
    onTimeError("");
  };
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="sm:col-span-2 text-xs text-slate-400">日程标题<input value={String(payload.title ?? "")} onChange={(event) => setField("title", event.target.value)} className={inputClass} /></label>
      <label className="text-xs text-slate-400">开始时间（{timezone}）<input type="datetime-local" value={toLocalInput(time.start_at, timezone)} onChange={(event) => setTime("start_at", event.target.value)} className={inputClass} /></label>
      <label className="text-xs text-slate-400">结束时间（{timezone}）<input type="datetime-local" value={toLocalInput(time.end_at, timezone)} onChange={(event) => setTime("end_at", event.target.value)} className={inputClass} /></label>
      {actionType === "create_recurring_event" && <>
        <label className="text-xs text-slate-400">重复频率<select value={String(payload.frequency ?? "daily")} onChange={(event) => setField("frequency", event.target.value)} className={inputClass}><option value="daily">每天</option><option value="weekly">每周</option><option value="monthly">每月</option></select></label>
        <label className="text-xs text-slate-400">重复次数<input type="number" min="1" value={String(payload.occurrence_count ?? 1)} onChange={(event) => setField("occurrence_count", Number(event.target.value))} className={inputClass} /></label>
      </>}
    </div>
  );
}

export function ApprovalCard({ proposal, timezone = "Asia/Shanghai", busy = false, onDecision }: ApprovalCardProps) {
  const [editing, setEditing] = useState(false);
  const [targetEditorReady, setTargetEditorReady] = useState(true);
  const [editedPayload, setEditedPayload] = useState<Record<string, unknown>>(
    () => resolvedReviewPayload(proposal),
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [decisionMessage, setDecisionMessage] = useState("");
  const [hasInvalidTime, setHasInvalidTime] = useState(false);
  const [occurrenceIndex, setOccurrenceIndex] = useState(0);
  const [editBaseVersion, setEditBaseVersion] = useState(proposal.version);
  const staleEdit = editing && editBaseVersion !== proposal.version;
  const editorDetailsRef = useRef<HTMLDetailsElement>(null);
  const editorRootRef = useRef<HTMLDivElement>(null);
  const editEntryButtonRef = useRef<HTMLButtonElement>(null);
  const decisionStatusRef = useRef<HTMLParagraphElement>(null);
  const returnFocusToEditEntry = useRef(false);
  useEffect(() => {
    if (editing) {
      const firstField = editorRootRef.current
        ?.querySelector<HTMLElement>('input:not([disabled]), select:not([disabled]), textarea:not([disabled])');
      (firstField ?? editorRootRef.current)?.focus();
      return;
    }
    if (returnFocusToEditEntry.current) {
      editEntryButtonRef.current?.focus();
      returnFocusToEditEntry.current = false;
    }
  }, [editing, targetEditorReady]);
  useEffect(() => {
    if (decisionMessage) decisionStatusRef.current?.focus();
  }, [decisionMessage]);
  const awaiting = proposal.status === "awaiting_approval";
  const conflicts = Array.isArray(proposal.display_context.conflicts)
    ? proposal.display_context.conflicts
    : [];
  const conflictDetails = conflictDisplayItems(conflicts);
  const reviewItems = actionReviewItems(proposal.display_context.review_items);
  const actionTitle = typeof proposal.display_context.action_title === "string"
    && proposal.display_context.action_title.trim()
    ? proposal.display_context.action_title.trim()
    : actionLabels[proposal.action_type] ?? "需要你确认的操作";
  const accessibleActionName = typeof proposal.display_context.object_name === "string"
    && proposal.display_context.object_name.trim()
    ? proposal.display_context.object_name.trim()
    : actionTitle;
  const actionSummary = typeof proposal.display_context.action_summary === "string"
    && proposal.display_context.action_summary.trim()
    ? proposal.display_context.action_summary.trim()
    : actionSummaryFallbacks[proposal.action_type] ?? "请核对具体变化后再决定。";
  const reviewComplete = proposal.display_context.review_complete;
  const legacyCreateEventPreview = reviewComplete === undefined
    && proposal.action_type === "create_event"
    && typeof proposal.action_payload.title === "string"
    && typeof proposal.action_payload.start_at === "string"
    && typeof proposal.action_payload.end_at === "string";
  const legacyRecurringPreview = reviewComplete === undefined
    && proposal.action_type === "create_recurring_event"
    && recurringOccurrencePreviews(proposal.display_context.occurrences).length > 0;
  const hasReviewableChange = reviewComplete !== false
    && (reviewItems.length > 0 || legacyCreateEventPreview || legacyRecurringPreview);
  const allowedDecisions = Array.isArray(proposal.display_context.allowed_decisions)
    ? proposal.display_context.allowed_decisions
    : [];
  const showsConflictCheck = "conflict_check" in proposal.display_context;
  const conflictCheckComplete = !showsConflictCheck
    || proposal.display_context.conflict_check === "completed";
  const canApprove = allowedDecisions.includes("approve")
    && hasReviewableChange
    && conflictCheckComplete
    && conflicts.length === 0;
  const canEdit = allowedDecisions.includes("edit") && hasReviewableChange && [
    "create_event",
    "update_event",
    "create_recurring_event",
    "mutate_events",
    "create_task_batch",
    "update_reminder",
    "set_reminder_target",
  ].includes(proposal.action_type);
  const canReject = allowedDecisions.includes("reject");
  const occurrences = recurringOccurrencePreviews(proposal.display_context.occurrences);
  const displayedOccurrences = occurrences;
  const selectedOccurrence = displayedOccurrences[
    Math.min(occurrenceIndex, Math.max(displayedOccurrences.length - 1, 0))
  ];

  const submitEdit = async () => {
    if (staleEdit) {
      setError("审批内容已更新。请取消编辑并重新打开，以载入最新版本。此次修改尚未提交。");
      return;
    }
    if (hasInvalidTime || !targetEditorReady) return;
    try {
      const timeError = editedPayloadTimeError(proposal.action_type, editedPayload);
      if (timeError) throw new Error(timeError);
      if (
        ["create_event", "create_recurring_event"].includes(proposal.action_type)
        && !editedPayload.title
      ) {
        throw new Error("请填写日程标题");
      }
      if (proposal.action_type === "create_task_batch") {
        const tasks = Array.isArray(editedPayload.tasks) ? editedPayload.tasks : [];
        if (!tasks.length || tasks.some((task) => (
          !task
          || typeof task !== "object"
          || typeof (task as Record<string, unknown>).title !== "string"
          || !(task as Record<string, unknown>).title?.toString().trim()
        ))) {
          throw new Error("请为每项任务填写名称");
        }
      }
      if (proposal.action_type === "update_reminder" && !String(editedPayload.title ?? "").trim()) {
        throw new Error("请填写提醒名称");
      }
      if (
        proposal.action_type === "set_reminder_target"
        && editedPayload.target_type !== "custom"
        && !editedPayload.target_id
      ) {
        throw new Error("请选择提醒要关联的任务或日程");
      }
      setError("");
      const actionPayload = proposal.action_type === "mutate_events"
        ? {
          ...editedPayload,
          operations: (Array.isArray(editedPayload.operations) ? editedPayload.operations : []).map((item) => {
            if (!item || typeof item !== "object" || Array.isArray(item)) return item;
            const operation = { ...(item as Record<string, unknown>) };
            delete operation.editor_existing_time;
            return operation;
          }),
        }
        : editedPayload;
      const result = await onDecision("edit", { actionPayload });
      if (result?.proposal.status === "awaiting_approval") {
        const conflictsRemain = Array.isArray(result.proposal.display_context.conflicts)
          && result.proposal.display_context.conflicts.length > 0;
        const refreshedReview = typeof result.proposal.display_context.review_notice === "string";
        if (refreshedReview) {
          setEditedPayload(resolvedReviewPayload(result.proposal));
          setEditBaseVersion(result.proposal.version);
        }
        setError(refreshedReview
          ? "日程版本已更新；审批保持待处理，请核对最新安排后再次确认。"
          : conflictsRemain
            ? "新时间仍有冲突；审批保持待处理，请继续调整。"
            : "暂时无法完整核对这项修改；审批保持待处理，请检查参数后重试。");
        return;
      }
      setEditing(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "修改未保存或未获批，请检查输入后重试。");
    }
  };

  const submitDecision = async (decision: "approve" | "reject") => {
    try {
      setError("");
      const result = await onDecision(decision, decision === "reject" ? { reason } : undefined);
      setDecisionMessage(decision === "reject"
        ? "已提交拒绝决定。"
        : result?.proposal.status === "executed"
          ? "操作已完成。"
        : result?.proposal.status === "failed"
          ? "已完成审批处理，但执行结果需要进一步核对。"
          : result?.proposal.status === "awaiting_approval"
            ? result.proposal.action_type === "apply_schedule_plan"
              ? "计划内容已有更新，审批仍待处理；请核对上方最新预览。"
              : "操作内容已有更新，审批仍待处理；请核对上方最新预览。"
          : "已提交审批，正在处理操作。");
    } catch {
      setError("这项操作没有完成，请重试。");
    }
  };

  return (
    <article data-surface="decision-surface" className="rounded-xl border border-amber-300/50 bg-amber-50 p-4 lg:rounded-2xl lg:border-amber-300/25 lg:bg-amber-300/5 lg:p-5 lg:shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex gap-3">
          <span className="rounded-xl bg-amber-300/10 p-2 text-amber-200"><ShieldAlert size={20} /></span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-amber-200">需要你确认</p>
            <h2 className="mt-1 font-semibold text-slate-100">
              {actionTitle}
            </h2>
          </div>
        </div>
        <span className="rounded-full bg-white/5 px-3 py-1 text-xs text-slate-300">
          {statusLabels[proposal.status]}
        </span>
      </div>

      <p className="mt-4 text-sm leading-6 text-slate-300">{actionSummary}</p>
      {typeof proposal.display_context.review_notice === "string" && (
        <p role="status" className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {proposal.display_context.review_notice}
        </p>
      )}
      {selectedOccurrence && (
        <section className="relative mt-4 border-y border-slate-200 py-3 pl-12 pr-12 lg:rounded-xl lg:border lg:border-cyan-300/20 lg:bg-cyan-300/5 lg:px-12 lg:py-4" aria-label="周期日程实例预览">
          <button
            type="button"
            aria-label={`查看上一个日程实例：${accessibleActionName}`}
            disabled={occurrenceIndex === 0}
            onClick={() => setOccurrenceIndex((current) => Math.max(0, current - 1))}
            className="absolute inset-y-0 left-1 grid w-11 place-items-center text-cyan-200 disabled:text-slate-700"
          >
            <ChevronLeft size={26} />
          </button>
          <div className="text-center">
          <h3 className="text-xs font-medium text-cyan-800 lg:text-cyan-200">周期日程 · 第 {selectedOccurrence.index} / {displayedOccurrences.length} 次</h3>
          <p className="mt-2 text-base font-semibold text-slate-100">{formatInUserTimezone(selectedOccurrence.start_at, timezone)} — {formatTimeInUserTimezone(selectedOccurrence.end_at, timezone)}</p>
            <p className={`mt-1 text-xs ${selectedOccurrence.conflicts.length > 0 ? "text-red-200" : "text-emerald-200"}`}>
              {selectedOccurrence.conflicts.length > 0 ? `此实例有 ${selectedOccurrence.conflicts.length} 个时间冲突` : "此实例暂无时间冲突"}
            </p>
          </div>
          <button
            type="button"
            aria-label={`查看下一个日程实例：${accessibleActionName}`}
            disabled={occurrenceIndex >= displayedOccurrences.length - 1}
            onClick={() => setOccurrenceIndex((current) => Math.min(displayedOccurrences.length - 1, current + 1))}
            className="absolute inset-y-0 right-1 grid w-11 place-items-center text-cyan-200 disabled:text-slate-700"
          >
            <ChevronRight size={26} />
          </button>
        </section>
      )}
      {proposal.action_type === "create_recurring_event" && !displayedOccurrences.length && <p className="mt-4 text-sm text-slate-300">共 {String(proposal.action_payload.occurrence_count ?? "多")} 次；详细日期暂不可用。</p>}
      {!editing && <section aria-label="变化预览" className="mt-4 border-t border-slate-200 pt-3 lg:rounded-xl lg:border lg:border-cyan-300/20 lg:bg-cyan-300/5 lg:p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-xs font-semibold text-cyan-800 lg:text-cyan-200">将要改变</h3>
          <p className="text-xs text-slate-500">时间按 {timezone} 显示</p>
        </div>
        <ActionReviewPreview items={reviewItems} timezone={timezone} />
        {reviewItems.length === 0 && ["create_event", "create_event_batch", "update_event", "mutate_events", "create_recurring_event"].includes(proposal.action_type)
          ? <PayloadSummary actionType={proposal.action_type} payload={resolvedReviewPayload(proposal)} timezone={timezone} />
          : reviewItems.length === 0 && <p className="text-sm text-slate-300">详细变化暂不可用，请展开操作详情。</p>}
      </section>}
      {showsConflictCheck && (
        <div className={`mt-3 rounded-xl border p-3 text-sm ${conflicts.length > 0 ? "border-red-300 bg-red-50 text-red-900" : "border-emerald-300 bg-emerald-50 text-emerald-900"}`}>
          {conflicts.length > 0
            ? <>
              <p>发现 {conflicts.length} 个时间冲突。请核对重叠时段，调整到无冲突时间，或拒绝这项操作。</p>
              <p className="mt-1 text-xs text-red-800">时间按 {timezone} 显示。</p>
              <ConflictDetails conflicts={conflictDetails} timezone={timezone} />
              {conflictDetails.length < conflicts.length && <p className="mt-2 text-xs text-red-800">部分冲突详情暂不可用。</p>}
            </>
            : proposal.display_context.conflict_check === "completed"
              ? "未发现日程冲突。"
              : "当前参数尚未完成冲突检查。"}
        </div>
      )}
      {showsConflictCheck && editing && <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
        当前冲突信息对应原安排。保存后会重新检查；无冲突时才批准。
      </p>}
      <details ref={editorDetailsRef} open={editing} className="approval-details mt-4 border-t border-slate-200 pt-3 lg:rounded-xl lg:border lg:border-white/10 lg:p-4">
        <summary className="min-h-11 cursor-pointer text-sm font-medium text-slate-300">查看操作详情：{accessibleActionName}</summary>
        <div ref={editorRootRef} tabIndex={-1} role="group" aria-label="编辑操作参数" className="mt-3 outline-none">
        <p className="text-xs text-slate-700">用户原始请求</p>
        <p className="mt-1 text-sm text-slate-200">{proposal.original_request}</p>
        <p className="mt-4 text-xs text-slate-700">提出时间</p>
        <p className="mt-1 text-sm text-slate-200">{formatInUserTimezone(proposal.created_at, timezone)}</p>
        <p className="mt-4 text-xs text-slate-700">拟执行参数</p>
        {editing ? (
          <div className="mt-3">
            {staleEdit && <div role="alert" className="mb-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950">
              <p>审批内容已更新。请取消编辑并重新打开，以载入最新版本；旧内容不会提交。</p>
              <ActionReviewPreview items={reviewItems} timezone={timezone} />
            </div>}
            <ApprovalEditor
              actionType={proposal.action_type}
              payload={editedPayload}
              timezone={timezone}
              onChange={(next) => { setEditedPayload(next); setError(""); }}
              onTimeError={(message) => { setError(message); setHasInvalidTime(Boolean(message)); }}
              onTargetEditorReady={setTargetEditorReady}
            />
          </div>
        ) : (
          <p className="mt-2 text-xs text-slate-700">具体字段请参考上方变化预览。</p>
        )}
        </div>
      </details>

      {awaiting && <p className="mt-3 flex items-center gap-2 text-xs text-slate-700">
        <Clock3 size={14} /> 在你确认前，这项操作不会执行。
      </p>}
      {proposal.error && proposal.action_type !== "apply_schedule_plan" && <p role="alert" className="mt-3 text-sm text-red-300">这项操作暂时没有完成，请重试或稍后再试。</p>}
      {(proposal.error || proposal.status === "failed") && proposal.action_type === "apply_schedule_plan" && (
        <div role="alert" className="mt-3 rounded-lg border border-amber-300/30 bg-amber-300/5 p-3 text-sm text-amber-100">
          <p>这次计划应用没有成功。请核对计划状态和任务时间，再决定是否调整并重新提交。</p>
          <a
            href={typeof proposal.action_payload.plan_id === "string"
              ? `/planning?plan_id=${encodeURIComponent(proposal.action_payload.plan_id)}`
              : "/planning"}
            className="mt-2 inline-flex min-h-11 items-center underline"
          >
            打开这份计划核对
          </a>
        </div>
      )}
      {decisionMessage && <p ref={decisionStatusRef} tabIndex={-1} role="status" className="mt-3 text-sm text-emerald-200">{decisionMessage}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}
      {awaiting && allowedDecisions.includes("approve") && !hasReviewableChange && (
        <p role="status" className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          暂时无法读取完整变化，因此不能确认这项操作。你可以拒绝，稍后重新发起。
        </p>
      )}
      {awaiting && allowedDecisions.includes("approve") && conflicts.length > 0 && (
        <p role="status" className="mt-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900">
          当前时间与已有日程冲突。请调整到无冲突时间，或拒绝这项操作。
        </p>
      )}
      {awaiting && allowedDecisions.includes("approve") && showsConflictCheck && !conflictCheckComplete && (
        <p role="status" className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          暂时无法确认这项日程是否冲突，因此不能继续确认。请稍后重试或拒绝。
        </p>
      )}

      {awaiting && (
        <div className="mt-5">
          {editing ? (
            <div className="flex flex-wrap gap-2">
              <button type="button" aria-label={`${conflicts.length > 0 ? "重新检查并批准" : "保存修改并批准"}：${accessibleActionName}`} disabled={busy || hasInvalidTime || !targetEditorReady || staleEdit} onClick={submitEdit} className="min-h-11 rounded-lg bg-amber-200 px-4 py-2 text-sm font-medium text-slate-950 disabled:opacity-50">{conflicts.length > 0 ? "重新检查并批准" : "保存修改并批准"}</button>
              <button type="button" aria-label={`取消编辑：${accessibleActionName}`} onClick={() => { setEditedPayload(resolvedReviewPayload(proposal)); setEditBaseVersion(proposal.version); setError(""); setHasInvalidTime(false); setTargetEditorReady(true); returnFocusToEditEntry.current = true; setEditing(false); }} className="min-h-11 rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300">取消编辑</button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {canApprove && <button type="button" aria-label={`确认并应用：${accessibleActionName}`} disabled={busy} onClick={() => void submitDecision("approve")} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-emerald-300 px-4 py-2 text-sm font-medium text-slate-950 disabled:opacity-50"><Check size={16} />确认并应用</button>}
              {canEdit && <button ref={editEntryButtonRef} type="button" aria-label={`${conflicts.length > 0 ? "先调整时间" : "调整后批准"}：${accessibleActionName}`} disabled={busy} onClick={() => { setEditedPayload(resolvedReviewPayload(proposal)); setEditBaseVersion(proposal.version); setTargetEditorReady(proposal.action_type !== "set_reminder_target"); returnFocusToEditEntry.current = false; setEditing(true); }} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-amber-300/30 px-4 py-2 text-sm text-amber-100 disabled:opacity-50"><Pencil size={16} />{conflicts.length > 0 ? "先调整时间" : "调整后批准"}</button>}
              {canReject && <button type="button" aria-label={`拒绝：${accessibleActionName}`} disabled={busy} onClick={() => void submitDecision("reject")} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-red-300/25 px-4 py-2 text-sm text-red-200 disabled:opacity-50"><X size={16} />拒绝</button>}
            </div>
          )}
          {!editing && canReject && (
            <input value={reason} onChange={(event) => setReason(event.target.value)} aria-label={`拒绝原因：${accessibleActionName}`} placeholder="拒绝原因（可选）" className="mt-3 min-h-11 w-full rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:border-red-300/40" />
          )}
        </div>
      )}
    </article>
  );
}
