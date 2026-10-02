import { CheckCircle2, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import type { InteractionArtifact } from "../../api/interactions";
import {
  ensureInteraction,
  recordInteractionTelemetry,
  submitInteraction,
} from "../../api/interactions";
import { getDurationRecommendation } from "../../api/time-memory";
import type { DurationRecommendation } from "../../api/time-memory";
import { ApiError } from "../../api/client";
import { getTask, getTaskExecutionSummary } from "../../api/tasks";

function key() {
  return globalThis.crypto?.randomUUID?.() ?? `check-in-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function telemetry(event: Parameters<typeof recordInteractionTelemetry>[0]) {
  void recordInteractionTelemetry(event).catch(() => undefined);
}

function eligibleMemorySuggestion(recommendation: DurationRecommendation | undefined) {
  if (!recommendation || recommendation.original_estimate_minutes === null) return false;
  if (recommendation.sample_count < 3 || recommendation.confidence < 0.65) return false;
  const base = recommendation.original_estimate_minutes;
  return recommendation.recommended_minutes >= base * 1.25 || recommendation.recommended_minutes <= base * 0.75;
}

function reasonText(reason: unknown) {
  const labels: Record<string, string> = {
    interrupted: "被打断",
    more_complex: "比预想复杂",
    low_energy: "状态不好",
    waiting: "等待他人",
    other: "其他",
  };
  return typeof reason === "string" ? labels[reason] ?? "" : "";
}

export type CompletionHarvestProps = {
  interaction: InteractionArtifact;
  onClose: (interaction: InteractionArtifact) => void;
  autoFocus?: boolean;
};

export function CompletionHarvest({
  interaction: initialInteraction,
  onClose,
  autoFocus = false,
}: CompletionHarvestProps) {
  const client = useQueryClient();
  const [interaction, setInteraction] = useState(initialInteraction);
  const taskId = initialInteraction.task_id ?? "";
  const task = useQuery({ queryKey: ["task", taskId], queryFn: () => getTask(taskId), enabled: Boolean(taskId), retry: false });
  const execution = useQuery({ queryKey: ["task-execution-summary", taskId], queryFn: () => getTaskExecutionSummary(taskId), enabled: Boolean(taskId), retry: false });
  const recommendation = useQuery({
    queryKey: ["duration-recommendation", taskId],
    queryFn: () => getDurationRecommendation(taskId),
    enabled: Boolean(taskId && interaction.payload.completion_feedback),
    retry: false,
  });
  const [rating, setRating] = useState(String(interaction.payload.completion_feedback && typeof interaction.payload.completion_feedback === "object"
    ? (interaction.payload.completion_feedback as Record<string, unknown>).rating ?? ""
    : ""));
  const [reason, setReason] = useState(String(interaction.payload.completion_feedback && typeof interaction.payload.completion_feedback === "object"
    ? (interaction.payload.completion_feedback as Record<string, unknown>).reason ?? ""
    : ""));
  const [celebrate, setCelebrate] = useState(false);
  const [reasonOpen, setReasonOpen] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const feedbackStatusRef = useRef<HTMLParagraphElement>(null);
  const wasFeedbackSaved = useRef(false);
  const feedbackSaved = Boolean(interaction.payload.completion_feedback);
  const plannedMinutes = useMemo(() => {
    const current = task.data;
    if (!current) return null;
    if (current.planned_start_at && current.planned_end_at) {
      return Math.round((new Date(current.planned_end_at).getTime() - new Date(current.planned_start_at).getTime()) / 60_000);
    }
    return current.estimated_minutes ?? null;
  }, [task.data]);
  const actualMinutes = execution.data && execution.data.evidence_status !== "no_execution_evidence"
    && execution.data.active_seconds > 0
    ? Math.round(execution.data.active_seconds / 60)
    : null;

  useEffect(() => {
    setInteraction(initialInteraction);
  }, [initialInteraction]);

  useEffect(() => {
    telemetry({ event_type: "interaction_shown", interaction_type: "task_completion" });
  }, [initialInteraction]);

  useEffect(() => {
    if (autoFocus) {
      document.getElementById(`completion-feedback-heading-${initialInteraction.id}`)?.focus();
    }
  }, [autoFocus, initialInteraction.id]);

  useEffect(() => {
    if (feedbackSaved && !wasFeedbackSaved.current) {
      window.requestAnimationFrame(() => feedbackStatusRef.current?.focus());
    }
    wasFeedbackSaved.current = feedbackSaved;
  }, [feedbackSaved]);

  useEffect(() => {
    if (!celebrate) return;
    const timer = window.setTimeout(() => setCelebrate(false), 700);
    return () => window.clearTimeout(timer);
  }, [celebrate]);

  const begin = () => {
    if (startedAt) return startedAt;
    const now = Date.now();
    setStartedAt(now);
    telemetry({ event_type: "interaction_started", interaction_type: "task_completion" });
    return now;
  };

  const submitFeedback = async () => {
    if (!rating) {
      setError("请选择一个选项；也可以直接跳过反馈。任务已经完成。");
      return;
    }
    begin();
    setError("");
    try {
      const result = await submitInteraction(interaction.id, {
        expected_version: interaction.version,
        action: "submit_feedback",
        values: { rating, ...(reason ? { reason } : {}) },
        idempotency_key: key(),
      });
      if (!result.accepted) throw new Error(result.detail ?? "反馈未能保存。");
      setInteraction(result.interaction);
      setMessage("反馈已记录，任务完成状态没有改变。");
      setCelebrate(true);
      await client.invalidateQueries({ queryKey: ["duration-recommendation", taskId] });
      setStartedAt(null);
    } catch (caught) {
      setError(caught instanceof ApiError && caught.status === 409
        ? "这张反馈卡已更新，请重新载入后再试。"
        : caught instanceof Error ? caught.message : "暂时无法保存反馈。");
    }
  };

  const dismiss = async () => {
    try {
      const result = await submitInteraction(interaction.id, {
        expected_version: interaction.version,
        action: "dismiss",
        values: {},
        idempotency_key: key(),
      });
      if (result.accepted) {
        onClose(result.interaction);
      }
    } catch {
      setError("暂时无法关闭反馈卡，请稍后重试。");
    }
  };

  const recommendationData = recommendation.data;
  const showMemorySuggestion = feedbackSaved && eligibleMemorySuggestion(recommendationData);

  return (
    <section className="mx-auto mt-4 w-full max-w-3xl rounded-2xl border border-emerald-300/20 bg-slate-950/90 p-4 shadow-lg sm:p-5" aria-label="任务完成反馈">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <CheckCircle2 className={`mt-0.5 shrink-0 text-emerald-300 ${celebrate ? "motion-safe:animate-pulse" : ""}`} size={22} />
          <div className="min-w-0">
            <h3 id={`completion-feedback-heading-${initialInteraction.id}`} tabIndex={-1} className="font-semibold text-white">{task.data?.title ?? "任务已完成"}</h3>
            <p className="mt-1 text-xs text-slate-400">这是可选反馈；任务已经完成，可以跳过。</p>
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
        <p className="rounded-lg bg-white/5 p-3 text-slate-300">计划时长：{plannedMinutes === null ? "未设置" : `${plannedMinutes} 分钟`}</p>
        <p className="rounded-lg bg-white/5 p-3 text-slate-300">
          实际投入：{actualMinutes === null ? "暂无计时证据" : `${actualMinutes} 分钟`}
          {execution.data?.evidence_status === "recording" && "（计时仍在进行）"}
        </p>
      </div>

      {!feedbackSaved ? (
        <>
          <fieldset className="mt-4">
            <legend className="text-sm font-medium text-slate-200">这次用时如何？</legend>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {([
                ["faster", "比预计快"],
                ["about_right", "差不多"],
                ["longer", "比预计久"],
              ] as const).map(([value, label]) => (
                <button key={value} type="button" aria-pressed={rating === value} onClick={() => { begin(); setRating(value); setError(""); }} className={`min-h-12 rounded-xl border px-2 text-sm ${rating === value ? "border-emerald-200 bg-emerald-300/15 text-emerald-100" : "border-white/10 text-slate-300 hover:bg-white/5"}`}>
                  {label}
                </button>
              ))}
            </div>
          </fieldset>
          <button type="button" aria-expanded={reasonOpen} onClick={() => setReasonOpen((open) => !open)} className="mt-3 min-h-11 rounded-lg px-2 text-sm text-slate-400 underline underline-offset-4">{reasonOpen ? "收起原因选项" : reason ? "修改原因（可选）" : "补充原因（可选）"}</button>
          {reasonOpen || reason ? <label className="mt-2 block text-sm text-slate-300">
            补充原因（可选）
            <select value={reason} onChange={(event) => { begin(); setReason(event.target.value); }} className="mt-1 min-h-11 w-full rounded-lg border border-white/10 bg-slate-900 px-3">
              <option value="">不填写</option>
              <option value="interrupted">被打断</option>
              <option value="more_complex">比预想复杂</option>
              <option value="low_energy">状态不好</option>
              <option value="waiting">等待他人</option>
              <option value="other">其他</option>
            </select>
          </label> : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" onClick={submitFeedback} className="min-h-11 rounded-xl bg-emerald-300 px-4 font-semibold text-slate-950">记录反馈</button>
            <button type="button" onClick={dismiss} className="min-h-11 rounded-xl border border-white/10 px-4 text-sm text-slate-300">跳过</button>
          </div>
        </>
      ) : (
        <>
          <p ref={feedbackStatusRef} tabIndex={-1} role="status" className="mt-4 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-emerald-200 text-sm text-emerald-200">
            已记录：{rating === "faster" ? "比预计快" : rating === "longer" ? "比预计久" : "差不多"}{reason ? ` · ${reasonText(reason)}` : ""}
          </p>
          {showMemorySuggestion && recommendationData && (
            <MemorySuggestionCard
              taskId={taskId}
              recommendation={recommendationData}
              onDone={dismiss}
            />
          )}
          {!showMemorySuggestion && !recommendation.isPending && <p className="mt-3 text-xs text-slate-400">目前没有足够的历史证据提出后续估时建议。</p>}
          {!showMemorySuggestion && <button type="button" onClick={dismiss} className="mt-4 min-h-11 rounded-xl border border-white/10 px-4 text-sm text-slate-300">完成</button>}
        </>
      )}
      {message && <p role="status" className="mt-3 text-xs text-emerald-200">{message}</p>}
      {error && <p role="alert" className="mt-3 text-xs text-amber-200">{error}</p>}
    </section>
  );
}

export type MemorySuggestionProps = {
  taskId: string;
  recommendation: DurationRecommendation;
  onDone: () => void;
};

export function MemorySuggestionCard({
  taskId,
  recommendation,
  onDone,
}: MemorySuggestionProps) {
  const [interaction, setInteraction] = useState<InteractionArtifact | null>(null);
  const [error, setError] = useState("");
  const delta = recommendation.original_estimate_minutes
    ? Math.round((recommendation.recommended_minutes / recommendation.original_estimate_minutes - 1) * 100)
    : 0;
  useEffect(() => {
    let active = true;
    void ensureInteraction({ type: "memory_suggestion", task_id: taskId })
      .then((result) => { if (active) setInteraction(result); })
      .catch(() => { if (active) setError("暂时无法恢复这条估时建议。"); });
    return () => { active = false; };
  }, [taskId]);

  const memoryInteractionId = interaction?.id;
  const memoryInteractionType = interaction?.type;
  useEffect(() => {
    if (memoryInteractionId && memoryInteractionType) {
      telemetry({ event_type: "memory_suggestion_shown", interaction_type: memoryInteractionType });
    }
  }, [memoryInteractionId, memoryInteractionType]);

  const decide = async (accept: boolean) => {
    if (!interaction) return;
    setError("");
    try {
      const result = await submitInteraction(interaction.id, {
        expected_version: interaction.version,
        action: accept ? "accept" : "dismiss",
        values: {},
        idempotency_key: key(),
      });
      if (accept && result.accepted) {
        onDone();
      } else if (!accept && result.accepted) {
        onDone();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "暂时无法保存选择。");
    }
  };

  return (
    <section className="mt-4 rounded-xl border border-cyan-200/20 bg-cyan-200/5 p-3" aria-label="估时建议">
      <div className="flex items-center gap-2 text-sm font-medium text-cyan-100"><Sparkles size={16} />最近 {recommendation.sample_count} 个类似任务样本</div>
      <p className="mt-2 text-sm text-slate-200">
        建议以后为这类任务预留 {recommendation.recommended_minutes} 分钟（比当前估时{delta > 0 ? "长" : "短"}约 {Math.abs(delta)}%）。是否更新后续估时偏好？
      </p>
      <p className="mt-1 text-xs text-slate-400">只有你选择“更新偏好”后，才会保存这项估时调整。</p>
      {interaction?.status === "pending" ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" disabled={!interaction} onClick={() => decide(true)} className="min-h-11 rounded-lg bg-cyan-200 px-3 text-sm font-semibold text-slate-950 disabled:opacity-50">更新偏好</button>
          <button type="button" disabled={!interaction} onClick={() => decide(false)} className="min-h-11 rounded-lg border border-white/10 px-3 text-sm text-slate-300 disabled:opacity-50">保持现状</button>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <p role="status" className="text-xs text-emerald-200">{interaction?.status === "completed" ? "估时偏好已更新。" : "已保持现有估时偏好。"}</p>
          <button type="button" onClick={onDone} className="min-h-11 rounded-lg border border-white/10 px-3 text-sm text-slate-300">关闭</button>
        </div>
      )}
      {error && <p role="alert" className="mt-2 text-xs text-amber-200">{error}</p>}
    </section>
  );
}
