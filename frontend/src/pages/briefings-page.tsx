import { CalendarClock, FileText, LoaderCircle, MessageSquareText, Play } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { BriefingSectionKey, BriefingStyle } from "../api/briefings";
import { MarkdownMessage } from "../components/chat/markdown-message";
import {
  useBriefingDefinitions,
  useBriefingRuns,
  useCreateBriefingDefinition,
  useLaunchBriefing,
  useEveningBriefingPreview,
} from "../features/briefings/hooks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import { getLocalDateKey } from "../utils/datetime";

export function BriefingsPage() {
  const navigate = useNavigate();
  const preference = useCurrentUserPreference();
  const timezone = preference.data?.timezone
    ?? import.meta.env.VITE_DEFAULT_TIMEZONE
    ?? "Asia/Shanghai";
  const definitions = useBriefingDefinitions();
  const runs = useBriefingRuns();
  const createDefinition = useCreateBriefingDefinition();
  const launch = useLaunchBriefing();
  const eveningPreview = useEveningBriefingPreview();
  const [selectedDefinition, setSelectedDefinition] = useState<string>("");
  const [targetDate, setTargetDate] = useState(() => getLocalDateKey(new Date(), timezone));
  const [name, setName] = useState("每日简报");
  const [style, setStyle] = useState<BriefingStyle>("balanced");
  const [sections, setSections] = useState<BriefingSectionKey[]>([
    "calendar",
    "tasks",
    "weather",
    "news",
  ]);

  useEffect(() => {
    if (preference.data?.timezone) {
      setTargetDate(getLocalDateKey(new Date(), preference.data.timezone));
    }
  }, [preference.data?.timezone]);

  useEffect(() => {
    if (!selectedDefinition && definitions.data?.[0]) {
      setSelectedDefinition(definitions.data[0].id);
    }
  }, [definitions.data, selectedDefinition]);

  const recentRuns = useMemo(() => runs.data?.slice(0, 12) ?? [], [runs.data]);

  const saveDefinition = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || sections.length === 0) return;
    const created = await createDefinition.mutateAsync({
      name: name.trim(),
      enabled_sections: sections,
      style,
      include_empty_sections: false,
      locale: "",
      timezone: "",
    });
    setSelectedDefinition(created.id);
  };

  const runNow = async () => {
    const response = await launch.mutateAsync({
      definitionId: selectedDefinition || null,
      targetDate,
    });
    navigate(`/chat/${response.conversation.id}`);
  };

  const toggleSection = (key: BriefingSectionKey) => {
    setSections((current) => current.includes(key)
      ? current.filter((item) => item !== key)
      : [...current, key]);
  };

  return (
    <section className="mx-auto max-w-6xl space-y-6">
      <header>
        <p className="text-sm font-medium text-cyan-300">Briefing Workflow</p>
        <h2 className="mt-1 text-2xl font-semibold">简报</h2>
        <p className="mt-2 text-sm text-slate-400">并行收集日程、任务、天气和关注新闻，再由受限 Editor 整理重点。</p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
        <div className="space-y-5">
          <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-5">
            <h3 className="flex items-center gap-2 font-medium"><CalendarClock size={18} className="text-cyan-300" />立即生成</h3>
            <label className="mt-4 block text-xs text-slate-400">简报配置
              <select value={selectedDefinition} onChange={(event) => setSelectedDefinition(event.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-sm">
                <option value="">默认每日简报</option>
                {definitions.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            <label className="mt-4 block text-xs text-slate-400">目标日期
              <input type="date" value={targetDate} onChange={(event) => setTargetDate(event.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-sm" />
            </label>
            <button type="button" onClick={runNow} disabled={launch.isPending} className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-300 px-4 py-2.5 text-sm font-medium text-slate-950 disabled:opacity-50">
              {launch.isPending ? <LoaderCircle size={17} className="animate-spin" /> : <Play size={17} />} 立即生成
            </button>
          </div>

          <div className="rounded-2xl border border-amber-300/20 bg-amber-300/5 p-5">
            <h3 className="font-medium text-amber-100">今日收尾</h3>
            <p className="mt-2 text-xs leading-5 text-slate-400">确定性汇总今日安排、未完成任务和仍有效的时间风险，不调用模型。</p>
            {eveningPreview.isLoading && <p className="mt-3 text-xs text-slate-500">正在读取…</p>}
            {eveningPreview.data && (
              <div className="mt-3 space-y-2 text-sm text-slate-300">
                <p>{eveningPreview.data.events.length} 个日程 · {eveningPreview.data.tasks.length} 个未完成任务 · {eveningPreview.data.insights.length} 条风险</p>
                {eveningPreview.data.insights.slice(0, 2).map((insight) => <p key={String(insight.id)} className="text-amber-100">{String(insight.title)}</p>)}
              </div>
            )}
            {eveningPreview.isError && <p className="mt-3 text-xs text-red-200">收尾摘要暂时不可用。</p>}
          </div>

          <form onSubmit={saveDefinition} className="rounded-2xl border border-white/10 bg-slate-900/60 p-5">
            <h3 className="font-medium">新建简报配置</h3>
            <label className="mt-4 block text-xs text-slate-400">名称
              <input value={name} onChange={(event) => setName(event.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-sm" />
            </label>
            <fieldset className="mt-4"><legend className="text-xs text-slate-400">数据 Section</legend>
              <div className="mt-2 flex flex-wrap gap-4 text-sm">
                {(["calendar", "tasks", "weather", "news"] as const).map((key) => {
                  const labels = { calendar: "日程", tasks: "任务", weather: "天气", news: "新闻" };
                  return <label key={key} className="flex items-center gap-2"><input type="checkbox" checked={sections.includes(key)} onChange={() => toggleSection(key)} />{labels[key]}</label>;
                })}
              </div>
            </fieldset>
            <label className="mt-4 block text-xs text-slate-400">表达风格
              <select value={style} onChange={(event) => setStyle(event.target.value as BriefingStyle)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-sm">
                <option value="concise">精简</option><option value="balanced">均衡</option><option value="detailed">详细</option>
              </select>
            </label>
            <button type="submit" disabled={createDefinition.isPending || sections.length === 0} className="mt-4 w-full rounded-xl border border-cyan-300/30 px-4 py-2 text-sm text-cyan-200 disabled:opacity-50">保存配置</button>
          </form>
        </div>

        <div className="space-y-4">
          <h3 className="flex items-center gap-2 font-medium"><FileText size={18} className="text-cyan-300" />最近简报</h3>
          {runs.isLoading && <p className="text-sm text-slate-500">正在加载简报…</p>}
          {!runs.isLoading && recentRuns.length === 0 && <div className="rounded-2xl border border-dashed border-white/10 p-10 text-center text-sm text-slate-500">还没有生成过简报。</div>}
          {recentRuns.map((run) => (
            <article key={run.id} className="rounded-2xl border border-white/10 bg-slate-900/60 p-5">
              <div className="flex flex-wrap items-center gap-3">
                <h4 className="font-medium">{run.target_date} 简报</h4>
                <span className={`rounded-full px-2 py-1 text-xs ${run.status === "failed" ? "bg-red-400/10 text-red-200" : run.status === "partial" ? "bg-amber-400/10 text-amber-200" : "bg-emerald-400/10 text-emerald-200"}`}>{run.status}</span>
                {run.conversation_id && <button type="button" onClick={() => navigate(`/chat/${run.conversation_id}`)} className="ml-auto flex items-center gap-1 text-xs text-cyan-300"><MessageSquareText size={14} />在聊天中继续</button>}
              </div>
              {run.rendered_markdown && <div className="mt-4 rounded-xl bg-slate-950/50 p-4"><MarkdownMessage content={run.rendered_markdown} /></div>}
              <div className="mt-4 flex flex-wrap gap-2">
                {run.section_runs.flatMap((section) => section.source_references).map((source) => {
                  const labels = { calendar_event: "日程", task: "任务", weather_forecast: "天气", news_article: "新闻" };
                  const content = <>{labels[source.kind]} · {source.title}{source.publisher ? ` · ${source.publisher}` : ""}</>;
                  return source.url
                    ? <a key={`${source.kind}-${source.id}`} href={source.url} target="_blank" rel="noreferrer" className="rounded-lg bg-white/5 px-2 py-1 text-xs text-cyan-300 hover:bg-white/10">{content}</a>
                    : <span key={`${source.kind}-${source.id}`} className="rounded-lg bg-white/5 px-2 py-1 text-xs text-slate-400">{content}</span>;
                })}
              </div>
              {run.warnings.map((warning) => <p key={warning} className="mt-2 text-xs text-amber-300">{warning}</p>)}
              {run.failure_message && <p className="mt-3 text-sm text-red-200">{run.failure_message}</p>}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
