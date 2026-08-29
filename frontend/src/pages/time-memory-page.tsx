import {
  Brain,
  CalendarClock,
  Check,
  MapPin,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import type { ReactNode } from "react";

import { parseTimeMemoryProfile } from "../api/time-memory";
import type { BehaviorWindow } from "../api/time-memory";
import {
  useCurrentUserPreference,
  useUpdateCurrentUserPreference,
} from "../features/preferences/hooks";
import {
  useClearCurrentTimeMemory,
  useCurrentTimeMemory,
  useForgetTimeMemoryPattern,
  useForgetTimeMemoryPlace,
  useDecisionProfile,
  useRecordDecisionFeedback,
} from "../features/preferences/time-memory-hooks";

const WINDOW_LABELS = { "7d": "最近 7 天", "30d": "最近 30 天", "180d": "最近 180 天" } as const;

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function percent(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

function statusLabel(status: string) {
  return {
    clean: "已同步",
    dirty: "等待更新",
    processing: "更新中",
    failed: "更新失败",
  }[status] ?? status;
}

function statusClass(status: string) {
  return status === "failed"
    ? "text-red-200"
    : status === "processing"
      ? "text-amber-200"
      : "text-emerald-200";
}

function patternStatusLabel(status: string) {
  return { active: "活跃", weakening: "正在减弱", expired: "已过期" }[status] ?? status;
}

export function TimeMemoryPage() {
  const memory = useCurrentTimeMemory();
  const preference = useCurrentUserPreference();
  const updatePreference = useUpdateCurrentUserPreference();
  const clearMemory = useClearCurrentTimeMemory();
  const forgetPlace = useForgetTimeMemoryPlace();
  const forgetPattern = useForgetTimeMemoryPattern();
  const decisionProfile = useDecisionProfile();
  const recordFeedback = useRecordDecisionFeedback();
  const profile = parseTimeMemoryProfile(memory.data?.profile);
  const isBusy =
    updatePreference.isPending
    || clearMemory.isPending
    || forgetPlace.isPending
    || forgetPattern.isPending
    || recordFeedback.isPending;

  const updateMemoryPreference = (
    field: "time_memory_enabled" | "time_memory_allow_generation" | "time_memory_allow_context_injection",
    value: boolean,
  ) => {
    updatePreference.mutate({ [field]: value });
  };

  const handleClear = () => {
    if (!window.confirm("确定清空全部时间行为画像吗？清空后会从新的时间点重新积累。")) return;
    clearMemory.mutate();
  };

  const handleForgetPlace = (placeId: string, name: string) => {
    if (!window.confirm(`确定从长期记忆中删除“${name}”吗？`)) return;
    forgetPlace.mutate(placeId);
  };

  const handleForgetPattern = (patternId: string) => {
    if (!window.confirm("确定删除这条稳定规律吗？后续重建也会继续排除它。")) return;
    forgetPattern.mutate(patternId);
  };

  if (memory.isLoading || preference.isLoading) {
    return <p className="text-slate-400">正在读取时间行为画像…</p>;
  }

  if (memory.isError || preference.isError) {
    return (
      <section className="mx-auto max-w-4xl">
        <h2 className="text-3xl font-semibold">时间行为记忆</h2>
        <div role="alert" className="mt-6 rounded-2xl border border-red-300/20 bg-red-400/10 p-5 text-red-200">
          无法读取记忆画像，请确认已登录后重试。
        </div>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-4xl space-y-6">
      <header>
        <p className="text-sm font-medium text-cyan-300">Time Steward</p>
        <h2 className="mt-2 text-3xl font-semibold">时间行为记忆</h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
          这里展示系统根据你的真实日程、任务和提醒统计出的时间管理习惯。它只作为聊天建议的背景，不会代替当前日程，也不会自动修改安排。
        </p>
      </header>

      <section className="rounded-2xl border border-white/10 bg-slate-900 p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-cyan-300/15 text-cyan-300">
            <Brain size={21} />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="font-semibold text-slate-100">记忆权限</h3>
            <p className="mt-1 text-sm leading-6 text-slate-400">你可以分别控制是否生成画像，以及是否把画像提供给 Time Steward。</p>
          </div>
        </div>
        <div className="mt-5 divide-y divide-white/10">
          <MemoryToggle
            checked={preference.data?.time_memory_enabled ?? true}
            disabled={isBusy}
            label="启用长期时间记忆"
            description="关闭后停止生成、读取和注入；现有画像不会继续用于对话。"
            onChange={(value) => updateMemoryPreference("time_memory_enabled", value)}
          />
          <MemoryToggle
            checked={preference.data?.time_memory_allow_generation ?? true}
            disabled={isBusy || !preference.data?.time_memory_enabled}
            label="允许生成画像"
            description="关闭后删除派生画像，但不删除你的日程、任务或提醒。"
            onChange={(value) => updateMemoryPreference("time_memory_allow_generation", value)}
          />
          <MemoryToggle
            checked={preference.data?.time_memory_allow_context_injection ?? true}
            disabled={isBusy || !preference.data?.time_memory_enabled}
            label="允许注入聊天上下文"
            description="关闭后仍可生成和查看画像，但聊天助手不会读取它。"
            onChange={(value) => updateMemoryPreference("time_memory_allow_context_injection", value)}
          />
        </div>
        {updatePreference.isError && <p role="alert" className="mt-4 text-sm text-red-200">权限保存失败：{updatePreference.error.message}</p>}
        {updatePreference.isSuccess && <p role="status" className="mt-4 text-sm text-emerald-200">记忆权限已更新。</p>}
      </section>

      <section className="rounded-2xl border border-white/10 bg-slate-900 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-semibold text-slate-100">时间决策建议</h3>
            <p className="mt-1 text-sm leading-6 text-slate-400">
              只使用可审计的执行证据与明确反馈，不保存原始推理，也不会自动修改任务或日程。
            </p>
          </div>
          <span className="text-xs text-slate-500">{decisionProfile.data?.source ?? "读取中"}</span>
        </div>
        {decisionProfile.isError ? (
          <p role="alert" className="mt-4 text-sm text-red-200">暂时无法读取建议状态。</p>
        ) : decisionProfile.data ? (
          <div className="mt-4 space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <StatCard label="建议倍率" value={`${decisionProfile.data.duration_multiplier.toFixed(2)}x`} icon={<CalendarClock size={17} />} />
              <StatCard label="样本量" value={`${decisionProfile.data.sample_count} 个`} icon={<Sparkles size={17} />} />
              <StatCard label="置信度" value={percent(decisionProfile.data.confidence)} icon={<Check size={17} />} />
            </div>
            <p className="text-xs leading-5 text-slate-500">依据：{decisionProfile.data.evidence.join("；")}</p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={isBusy}
                onClick={() => recordFeedback.mutate({
                  category: "duration_estimate",
                  action: "accept",
                  value: {},
                  idempotency_key: `web-accept-${Date.now()}`,
                  source: "web",
                })}
                className="rounded-lg border border-emerald-300/30 px-3 py-2 text-xs text-emerald-200 hover:bg-emerald-300/10 disabled:opacity-50"
              >
                建议准确
              </button>
              <button
                type="button"
                disabled={isBusy}
                onClick={() => recordFeedback.mutate({
                  category: "duration_estimate",
                  action: "disable",
                  value: {},
                  idempotency_key: `web-disable-${Date.now()}`,
                  source: "web",
                })}
                className="rounded-lg border border-white/15 px-3 py-2 text-xs text-slate-300 hover:bg-white/5 disabled:opacity-50"
              >
                关闭此类建议
              </button>
            </div>
            {recordFeedback.isSuccess && <p role="status" className="text-xs text-emerald-200">反馈已记录。</p>}
            {recordFeedback.isError && <p role="alert" className="text-xs text-red-200">反馈保存失败：{recordFeedback.error.message}</p>}
          </div>
        ) : (
          <p className="mt-4 text-sm text-slate-500">正在读取建议状态…</p>
        )}
      </section>

      <section className="rounded-2xl border border-white/10 bg-slate-900 p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h3 className="font-semibold text-slate-100">画像状态</h3>
            <p className="mt-1 text-sm text-slate-400">
              状态：<span className={statusClass(memory.data?.refresh_status ?? "clean")}>{statusLabel(memory.data?.refresh_status ?? "clean")}</span>
            </p>
          </div>
          <div className="text-right text-xs text-slate-500">
            <p>最近完成：{formatDateTime(memory.data?.last_completed_at)}</p>
            {profile && <p className="mt-1">统计截止：{formatDateTime(profile.data_until)}</p>}
          </div>
        </div>
        {memory.data?.last_error && <p role="alert" className="mt-4 rounded-xl bg-red-400/10 p-3 text-sm text-red-200">{memory.data.last_error}</p>}
        {!profile ? (
          <div className="mt-5 rounded-xl border border-dashed border-white/15 p-6 text-center text-sm text-slate-400">
            当前还没有可展示的画像。开启记忆后，系统会在有足够业务数据时自动生成。
          </div>
        ) : (
          <>
            {profile.profile_summary && <p className="mt-5 rounded-xl bg-cyan-300/10 p-4 text-sm leading-6 text-cyan-100">{profile.profile_summary}</p>}
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <StatCard label="常用地点" value={`${profile.common_places.length} 个`} icon={<MapPin size={17} />} />
              <StatCard label="稳定规律" value={`${profile.stable_patterns.filter((item) => item.status === "active").length} 条`} icon={<Sparkles size={17} />} />
              <StatCard label="画像版本" value={`v${profile.version}`} icon={<RefreshCw size={17} />} />
            </div>
          </>
        )}
      </section>

      {profile && (
        <>
          <section className="rounded-2xl border border-white/10 bg-slate-900 p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <CalendarClock size={20} className="text-cyan-300" />
              <div>
                <h3 className="font-semibold text-slate-100">行为窗口</h3>
                <p className="mt-1 text-xs text-slate-500">按你的本地时区滚动计算，不是按服务器时区切分。</p>
              </div>
            </div>
            <div className="mt-5 grid gap-4 lg:grid-cols-3">
              {(["7d", "30d", "180d"] as const).map((windowName) => {
                const item = profile.behavior_windows[windowName];
                if (!item) return null;
                return <BehaviorWindowCard key={windowName} windowName={windowName} item={item} />;
              })}
            </div>
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <MemoryListCard title="常用地点" icon={<MapPin size={20} />} emptyText="暂无满足条件的常用地点。">
              {profile.common_places.map((place) => (
                <div key={place.place_id} className="flex items-start gap-3 border-b border-white/10 py-4 last:border-0">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-slate-100">{place.name}</p>
                    <p className="mt-1 text-xs leading-5 text-slate-500">{place.event_count} 次 · {place.total_scheduled_hours.toFixed(1)} 小时 · 置信度 {percent(place.confidence)}</p>
                    {place.typical_time_ranges.length > 0 && <p className="mt-1 text-xs text-slate-500">常见时段：{place.typical_time_ranges.join("、")}</p>}
                  </div>
                  <button type="button" disabled={isBusy} onClick={() => handleForgetPlace(place.place_id, place.name)} className="rounded-lg p-2 text-slate-500 hover:bg-red-400/10 hover:text-red-200 disabled:opacity-50" aria-label={`删除常用地点 ${place.name}`} title="删除这个地点">
                    <Trash2 size={17} />
                  </button>
                </div>
              ))}
            </MemoryListCard>

            <MemoryListCard title="稳定规律" icon={<Sparkles size={20} />} emptyText="目前还没有足够证据形成稳定规律。">
              {profile.stable_patterns.map((pattern) => (
                <div key={pattern.pattern_id} className="flex items-start gap-3 border-b border-white/10 py-4 last:border-0">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium text-slate-100">{pattern.summary}</p>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] ${pattern.status === "active" ? "bg-emerald-300/10 text-emerald-200" : "bg-slate-700 text-slate-300"}`}>{patternStatusLabel(pattern.status)}</span>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-slate-500">证据：{pattern.evidence_windows.join("、") || "暂无"} · 置信度 {percent(pattern.confidence)}</p>
                  </div>
                  <button type="button" disabled={isBusy} onClick={() => handleForgetPattern(pattern.pattern_id)} className="rounded-lg p-2 text-slate-500 hover:bg-red-400/10 hover:text-red-200 disabled:opacity-50" aria-label="删除这条稳定规律" title="删除这条规律">
                    <Trash2 size={17} />
                  </button>
                </div>
              ))}
            </MemoryListCard>
          </section>

          <section className="rounded-2xl border border-red-300/20 bg-red-400/5 p-5 sm:p-6">
            <h3 className="font-semibold text-red-100">清除画像</h3>
            <p className="mt-2 text-sm leading-6 text-slate-400">清空当前画像及主动排除记录。你的日程、任务和提醒不会被删除，系统之后会从新的时间点重新积累。</p>
            <button type="button" disabled={isBusy} onClick={handleClear} className="mt-4 rounded-xl border border-red-300/40 px-4 py-2.5 text-sm font-medium text-red-200 hover:bg-red-400/10 disabled:opacity-50">
              {clearMemory.isPending ? "清空中…" : "清空全部画像"}
            </button>
            {clearMemory.isError && <p role="alert" className="mt-3 text-sm text-red-200">清空失败：{clearMemory.error.message}</p>}
            {clearMemory.isSuccess && <p role="status" className="mt-3 text-sm text-emerald-200">画像已清空。</p>}
          </section>
        </>
      )}
    </section>
  );
}

function MemoryToggle({ checked, disabled, label, description, onChange }: { checked: boolean; disabled: boolean; label: string; description: string; onChange: (value: boolean) => void }) {
  return (
    <label className={`flex cursor-pointer items-start gap-4 py-4 ${disabled ? "cursor-not-allowed opacity-50" : ""}`}>
      <input aria-label={label} type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} className="peer sr-only" />
      <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-md border border-white/20 text-slate-950 peer-checked:border-cyan-300 peer-checked:bg-cyan-300">
        {checked && <Check size={14} strokeWidth={3} />}
      </span>
      <span>
        <span className="block text-sm font-medium text-slate-100">{label}</span>
        <span className="mt-1 block text-xs leading-5 text-slate-500">{description}</span>
      </span>
    </label>
  );
}

function StatCard({ label, value, icon }: { label: string; value: string; icon: ReactNode }) {
  return <div className="rounded-xl border border-white/10 bg-slate-950/50 p-4"><div className="flex items-center gap-2 text-cyan-300">{icon}<span className="text-xs text-slate-500">{label}</span></div><p className="mt-2 text-xl font-semibold text-slate-100">{value}</p></div>;
}

function BehaviorWindowCard({ windowName, item }: { windowName: keyof typeof WINDOW_LABELS; item: BehaviorWindow }) {
  const schedule = item.schedule_pattern;
  const planning = item.planning_pattern;
  const changes = item.change_pattern;
  const adaptive = item.adaptive_planning_pattern;
  return (
    <article className="rounded-xl border border-white/10 bg-slate-950/50 p-4">
      <div className="flex items-center justify-between gap-3"><h4 className="font-medium text-slate-100">{WINDOW_LABELS[windowName]}</h4><span className="text-xs text-slate-500">{percent(item.confidence)} 置信度</span></div>
      <p className="mt-1 text-xs text-slate-500">{item.start_date} 至 {item.end_date}</p>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm"><Metric label="日程" value={`${item.event_count} 项`} /><Metric label="日均占用" value={`${schedule.average_daily_scheduled_hours.toFixed(1)} 小时`} /><Metric label="忙碌日" value={`${schedule.busy_day_count} 天`} /><Metric label="任务" value={`${item.task_count} 项`} /></div>
      <div className="mt-4 space-y-2 text-xs leading-5 text-slate-400"><p><span className="text-slate-500">安排强度：</span>{schedule.summary}</p><p><span className="text-slate-500">规划方式：</span>{planning.summary}</p><p><span className="text-slate-500">调整情况：</span>{changes.summary}</p>{adaptive && <p><span className="text-slate-500">自动维护：</span>{adaptive.summary}</p>}</div>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg bg-white/5 p-2.5"><p className="text-[11px] text-slate-500">{label}</p><p className="mt-1 font-medium text-slate-200">{value}</p></div>;
}

function MemoryListCard({ title, icon, emptyText, children }: { title: string; icon: ReactNode; emptyText: string; children: ReactNode }) {
  const hasChildren = Boolean(children && (Array.isArray(children) ? children.length : true));
  return <section className="rounded-2xl border border-white/10 bg-slate-900 p-5 sm:p-6"><div className="flex items-center gap-3 text-cyan-300">{icon}<h3 className="font-semibold text-slate-100">{title}</h3></div>{hasChildren ? <div className="mt-2">{children}</div> : <p className="mt-5 text-sm text-slate-500">{emptyText}</p>}</section>;
}
