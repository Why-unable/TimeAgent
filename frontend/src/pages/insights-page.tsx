import {
  Ban,
  Check,
  Clock3,
  Flag,
  Lightbulb,
  MessageSquareText,
  RefreshCw,
} from "lucide-react";
import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import type { TemporalInsight } from "../api/insights";
import {
  useActOnTemporalInsight,
  useTemporalInsight,
  useTemporalInsights,
} from "../features/insights/hooks";

const severityStyle: Record<string, string> = {
  high: "border-rose-400/40 bg-rose-400/10 text-rose-100",
  medium: "border-amber-300/35 bg-amber-300/10 text-amber-100",
  low: "border-cyan-300/30 bg-cyan-300/10 text-cyan-100",
};

function evidenceSummary(insight: TemporalInsight): string {
  const evidence = insight.evidence as Record<string, unknown>;
  if (typeof evidence.due_at === "string") return `截止 ${new Date(evidence.due_at).toLocaleString("zh-CN")}`;
  if (typeof evidence.unplanned_minutes === "number") {
    return `未安排 ${evidence.unplanned_minutes} 分钟，可用 ${String(evidence.available_minutes ?? "-")} 分钟`;
  }
  return "由当前任务、日程与容量事实计算";
}

function primaryTarget(insight: TemporalInsight): string {
  const evidence = insight.evidence as Record<string, unknown>;
  if (insight.kind === "capacity_risk") return "/planning";
  if (typeof evidence.task_id === "string") return `/tasks?task=${encodeURIComponent(evidence.task_id)}`;
  return "/today";
}

export function InsightsPage() {
  const { insightId } = useParams<{ insightId?: string }>();
  const navigate = useNavigate();
  const insights = useTemporalInsights();
  const linkedInsight = useTemporalInsight(insightId);
  const action = useActOnTemporalInsight();
  const visibleInsights = useMemo(() => {
    const open = insights.data ?? [];
    const linked = linkedInsight.data;
    if (!linked || open.some((item) => item.id === linked.id)) return open;
    return [linked, ...open];
  }, [insights.data, linkedInsight.data]);

  const handleAction = (
    insight: TemporalInsight,
    actionName: "snooze" | "dismiss" | "actioned" | "false_positive",
    disableKind = false,
    destination?: string,
  ) => {
    action.mutate(
      { insightId: insight.id, input: { action: actionName, disable_kind: disableKind } },
      { onSuccess: () => destination && navigate(destination) },
    );
  };

  const continueInChat = (insight: TemporalInsight) => {
    const query = new URLSearchParams({ insight_id: insight.id, insight_title: insight.title });
    navigate(`/chat?${query.toString()}`);
  };

  if (insights.isLoading || (insightId && linkedInsight.isLoading)) {
    return <p className="text-slate-400">正在检查时间风险…</p>;
  }

  return (
    <div className="mx-auto max-w-4xl pb-24">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-white/10 pb-5">
        <div>
          <div className="flex items-center gap-2 text-amber-200">
            <Lightbulb size={20} />
            <span className="text-sm font-medium">时间洞察</span>
          </div>
          <h1 className="mt-2 text-2xl font-semibold text-slate-50">需要处理的风险</h1>
          <p className="mt-1 text-sm text-slate-400">这里只保留仍有行动空间、具有确定事实依据的项目。</p>
        </div>
        <button
          type="button"
          onClick={() => void insights.refetch()}
          disabled={insights.isFetching}
          title="重新扫描"
          className="inline-flex size-10 items-center justify-center rounded-lg border border-white/10 text-slate-300 hover:bg-white/5 disabled:opacity-50"
        >
          <RefreshCw size={17} className={insights.isFetching ? "animate-spin" : ""} />
        </button>
      </header>

      {visibleInsights.length === 0 ? (
        <section className="py-16 text-center">
          <Check className="mx-auto text-emerald-300" size={30} />
          <h2 className="mt-4 font-medium text-slate-100">当前没有待处理洞察</h2>
          <p className="mt-2 text-sm text-slate-500">新的临期、逾期或容量风险会出现在这里。</p>
        </section>
      ) : (
        <div className="mt-5 space-y-3">
          {visibleInsights.map((insight) => {
            const isHistorical = insight.status !== "open";
            return (
              <article
                key={insight.id}
                className={`border p-4 sm:p-5 ${
                  insight.id === insightId ? "border-cyan-300/50 bg-cyan-300/5" : "border-white/10 bg-slate-950/45"
                } ${isHistorical ? "opacity-70" : ""}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`border px-2 py-0.5 text-xs ${severityStyle[insight.severity] ?? severityStyle.low}`}>
                        {insight.severity === "high" ? "高风险" : insight.severity === "medium" ? "需留意" : "提示"}
                      </span>
                      {isHistorical && <span className="text-xs text-slate-500">状态：{insight.status}</span>}
                    </div>
                    <h2 className="mt-3 font-semibold text-slate-100">{insight.title}</h2>
                    <p className="mt-1 text-sm leading-6 text-slate-300">{insight.summary}</p>
                    <p className="mt-3 text-xs text-slate-500">依据：{evidenceSummary(insight)}</p>
                  </div>
                </div>

                {!isHistorical && (
                  <div className="mt-4 flex flex-wrap gap-2 border-t border-white/10 pt-4">
                    <button
                      type="button"
                      disabled={action.isPending}
                      onClick={() => handleAction(insight, "actioned", false, primaryTarget(insight))}
                      className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-cyan-300 px-3 text-sm font-medium text-slate-950 disabled:opacity-50"
                    >
                      <Check size={16} />处理
                    </button>
                    <button
                      type="button"
                      disabled={action.isPending}
                      onClick={() => continueInChat(insight)}
                      className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-cyan-300/30 px-3 text-sm text-cyan-100 disabled:opacity-50"
                    >
                      <MessageSquareText size={16} />分析选项
                    </button>
                    <button
                      type="button"
                      title="四小时后再显示"
                      disabled={action.isPending}
                      onClick={() => handleAction(insight, "snooze")}
                      className="inline-flex size-10 items-center justify-center rounded-lg border border-white/10 text-amber-200 disabled:opacity-50"
                    >
                      <Clock3 size={16} />
                    </button>
                    <button
                      type="button"
                      title="这条不准确"
                      disabled={action.isPending}
                      onClick={() => handleAction(insight, "false_positive")}
                      className="inline-flex size-10 items-center justify-center rounded-lg border border-white/10 text-rose-200 disabled:opacity-50"
                    >
                      <Flag size={16} />
                    </button>
                    <button
                      type="button"
                      title="关闭此类洞察"
                      disabled={action.isPending}
                      onClick={() => handleAction(insight, "false_positive", true)}
                      className="inline-flex size-10 items-center justify-center rounded-lg border border-white/10 text-slate-400 disabled:opacity-50"
                    >
                      <Ban size={16} />
                    </button>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
      {(insights.error || linkedInsight.error || action.error) && (
        <p role="alert" className="mt-4 text-sm text-rose-300">
          {(insights.error ?? linkedInsight.error ?? action.error)?.message}
        </p>
      )}
    </div>
  );
}
