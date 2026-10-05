import { Check, CheckCircle2, ChevronDown, Play } from "lucide-react";
import { Link } from "react-router-dom";

import { formatInUserTimezone, formatTimeInUserTimezone } from "../../utils/datetime";

export interface TodayExecutionItem {
  kind: "event" | "task";
  id: string;
  title: string;
  start_at: string | null;
  end_at: string | null;
  status: string | null;
  due_at: string | null;
}

function mobileChatIntentLink(prompt: string) {
  const query = new URLSearchParams({ auto_send: "1", prompt });
  return `/chat?${query.toString()}`;
}

function mobileEventAdjustmentLink(item: TodayExecutionItem, timezone: string) {
  return mobileChatIntentLink(
    `请检查日程「${item.title}」(event_id=${item.id}, ${item.start_at ?? "未记录开始时间"} 至 ${item.end_at ?? "未记录结束时间"}, 用户时区 ${timezone})周围的任务安排，并说明有哪些调整选择。先不要修改或应用。`,
  );
}

function executionTime(item: TodayExecutionItem, timezone: string) {
  if (item.start_at && item.end_at) {
    return `${formatTimeInUserTimezone(item.start_at, timezone)}–${formatTimeInUserTimezone(item.end_at, timezone)}`;
  }
  if (item.due_at) return `截止 ${formatInUserTimezone(item.due_at, timezone)}`;
  if (item.status === "in_progress") return "正在进行";
  return "待安排时间";
}

function chatIntentLink(prompt: string) {
  const query = new URLSearchParams({ auto_send: "1", prompt });
  return `/chat?${query.toString()}`;
}

function ExecutionItemCard({
  item,
  timezone,
  onComplete,
  onStart,
  busy,
}: {
  item: TodayExecutionItem;
  timezone: string;
  onComplete: (id: string) => void;
  onStart: (id: string) => void;
  busy: boolean;
}) {
  const isTask = item.kind === "task";
  const inProgress = item.status === "in_progress";
  return (
    <article className="flex min-w-0 items-center justify-between gap-3 rounded-xl border border-white/10 bg-slate-950/55 p-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-100">{item.title}</p>
        <p className="mt-1 text-xs text-slate-400">
          {item.kind === "event" ? "日程 · " : inProgress ? "进行中 · " : "任务 · "}
          {executionTime(item, timezone)}
        </p>
      </div>
      {isTask && (
        <div className="flex shrink-0 items-center gap-1">
          {!inProgress && (
            <button
              type="button"
              aria-label={`开始任务：${item.title}`}
              disabled={busy}
              onClick={() => onStart(item.id)}
              className="grid min-h-11 min-w-11 place-items-center rounded-lg text-cyan-200 hover:bg-cyan-300/10 disabled:opacity-50"
            >
              <Play size={17} />
            </button>
          )}
          <button
            type="button"
            aria-label={`完成任务：${item.title}`}
            disabled={busy}
            onClick={() => onComplete(item.id)}
            className="grid min-h-11 min-w-11 place-items-center rounded-lg text-emerald-200 hover:bg-emerald-300/10 disabled:opacity-50"
          >
            <CheckCircle2 size={18} />
          </button>
          <Link
            to="/tasks"
            aria-label={`查看任务：${item.title}`}
            className="inline-flex min-h-11 items-center rounded-lg px-2 text-xs font-medium text-slate-300 hover:bg-white/5"
          >
            任务
          </Link>
          <Link
            to={chatIntentLink(`请先核对任务「${item.title}」(task_id=${item.id})的当前状态和关联计划，再帮我评估如何调整后续安排。不要更改永久优先级，也不要未经我确认就应用正式日程。`)}
            aria-label={`让助理协助调整任务：${item.title}`}
            className="inline-flex min-h-11 items-center rounded-lg px-2 text-xs font-medium text-cyan-200 hover:bg-cyan-300/10"
          >
            调整
          </Link>
        </div>
      )}
      {item.kind === "event" && (
        <div className="flex shrink-0 items-center gap-1">
          <Link to="/calendar" className="inline-flex min-h-11 items-center rounded-lg px-3 text-xs font-medium text-cyan-200 hover:bg-cyan-300/10">
            查看日程
          </Link>
          <Link
            to={chatIntentLink(`请检查日程「${item.title}」(event_id=${item.id}, ${item.start_at ?? "未记录开始时间"} 至 ${item.end_at ?? "未记录结束时间"}, 用户时区 ${timezone})周围的任务安排，并说明有哪些调整选择。先不要修改或应用。`)}
            className="inline-flex min-h-11 items-center rounded-lg px-3 text-xs font-medium text-slate-300 hover:bg-white/5"
          >
            调整安排
          </Link>
        </div>
      )}
    </article>
  );
}

function ExecutionSection({
  title,
  items,
  timezone,
  onComplete,
  onStart,
  busy,
  emptyText,
  tone,
}: {
  title: string;
  items: TodayExecutionItem[];
  timezone: string;
  onComplete: (id: string) => void;
  onStart: (id: string) => void;
  busy: boolean;
  emptyText: string;
  tone: "teal" | "cyan" | "violet";
}) {
  const headingTone = {
    teal: "text-teal-200",
    cyan: "text-cyan-200",
    violet: "text-violet-200",
  }[tone];
  return (
    <section aria-label={title} className="rounded-2xl border border-white/10 bg-slate-900/80 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className={`text-sm font-semibold ${headingTone}`}>{title}</h3>
        <span className="text-xs text-slate-500">{items.length} 项</span>
      </div>
      {items.length === 0 ? (
        <p className="rounded-xl bg-slate-950/45 p-3 text-sm text-slate-500">{emptyText}</p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <ExecutionItemCard
              key={`${item.kind}:${item.id}`}
              item={item}
              timezone={timezone}
              onComplete={onComplete}
              onStart={onStart}
              busy={busy}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export function TodayExecutionSurface({
  now,
  next,
  later,
  timezone,
  onComplete,
  onStart,
  busy,
}: {
  now: TodayExecutionItem[];
  next: TodayExecutionItem[];
  later: TodayExecutionItem[];
  timezone: string;
  onComplete: (id: string) => void;
  onStart: (id: string) => void;
  busy: boolean;
}) {
  const common = { timezone, onComplete, onStart, busy };
  return (
    <section aria-label="今日执行面板" className="grid gap-3 2xl:grid-cols-3">
      <ExecutionSection
        {...common}
        title="现在"
        items={now}
        tone="teal"
        emptyText="当前没有进行中的日程或任务。"
      />
      <ExecutionSection
        {...common}
        title="接下来"
        items={next}
        tone="cyan"
        emptyText="后续暂无已安排事项。"
      />
      <ExecutionSection
        {...common}
        title="稍后"
        items={later}
        tone="violet"
        emptyText="后面没有其他安排。"
      />
    </section>
  );
}

function MobileExecutionRow({
  item,
  timezone,
  onComplete,
  onStart,
  busy,
}: {
  item: TodayExecutionItem;
  timezone: string;
  onComplete: (id: string) => void;
  onStart: (id: string) => void;
  busy: boolean;
}) {
  const isTask = item.kind === "task";
  const inProgress = item.status === "in_progress";
  return (
    <article className="flex min-h-14 min-w-0 items-center gap-3 border-b border-slate-200 py-2 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-900">{item.title}</p>
        <p className="mt-0.5 text-xs text-slate-600">
          {item.kind === "event" ? "日程 · " : inProgress ? "进行中 · " : "任务 · "}
          {executionTime(item, timezone)}
        </p>
      </div>
      {isTask ? (
        <div className="flex shrink-0 items-center gap-1">
          {!inProgress && (
            <button
              type="button"
              aria-label={`开始任务：${item.title}`}
              disabled={busy}
              onClick={() => onStart(item.id)}
              className="grid size-11 place-items-center rounded-lg text-teal-800 hover:bg-teal-50 disabled:opacity-50"
            >
              <Play size={17} aria-hidden="true" />
            </button>
          )}
          <button
            type="button"
            aria-label={`完成任务：${item.title}`}
            disabled={busy}
            onClick={() => onComplete(item.id)}
            className="grid size-11 place-items-center rounded-lg text-emerald-800 hover:bg-emerald-50 disabled:opacity-50"
          >
            <CheckCircle2 size={19} aria-hidden="true" />
          </button>
        </div>
      ) : (
        <Link
          to="/calendar"
          aria-label={`查看日程：${item.title}`}
          className="inline-flex min-h-11 shrink-0 items-center rounded-lg px-3 text-xs font-medium text-teal-800 hover:bg-teal-50"
        >
          查看
        </Link>
      )}
    </article>
  );
}

/** Mobile presentation chooses one item from server-owned buckets as the visual focus. */
export function MobileTodayExecutionSurface({
  now,
  next,
  later,
  timezone,
  onComplete,
  onStart,
  busy,
}: {
  now: TodayExecutionItem[];
  next: TodayExecutionItem[];
  later: TodayExecutionItem[];
  timezone: string;
  onComplete: (id: string) => void;
  onStart: (id: string) => void;
  busy: boolean;
}) {
  const current = now[0] ?? null;
  const nextFocus = current ? null : next[0] ?? null;
  const focus = current ?? nextFocus;
  const otherNow = current ? now.slice(1) : [];
  const remainingNext = current ? next : next.slice(1);
  const listProps = { timezone, onComplete, onStart, busy };

  return (
    <section aria-label="今日执行重点" className="space-y-5">
      {focus ? (
        <article data-testid="today-focus" data-surface="focus-card" className="rounded-2xl border border-teal-200 bg-white p-4 shadow-[0_8px_24px_-20px_rgba(15,23,42,0.35)]">
          <p className="text-xs font-semibold uppercase tracking-wide text-teal-800">
            {current ? (current.kind === "task" && current.status === "in_progress" ? "正在进行" : "现在") : "接下来"}
          </p>
          <h2 className="mt-2 break-words text-xl font-semibold leading-7 text-slate-900">{focus.title}</h2>
          <p className="mt-1.5 text-sm text-slate-600">{executionTime(focus, timezone)}</p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
      {focus.kind === "task" && (
              <>
                {focus.status !== "in_progress" && (
                  <button
                    type="button"
                    aria-label={`开始任务：${focus.title}`}
                    disabled={busy}
                    onClick={() => onStart(focus.id)}
                    className="mobile-on-brand inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50"
                  >
                    <Play size={17} aria-hidden="true" /> 开始
                  </button>
                )}
                <button
                  type="button"
                  aria-label={`完成任务：${focus.title}`}
                  disabled={busy}
                  onClick={() => onComplete(focus.id)}
                  className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold disabled:opacity-50 ${focus.status === "in_progress" ? "mobile-on-brand bg-teal-700 text-white hover:bg-teal-800" : "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50"}`}
                >
                  <Check size={17} aria-hidden="true" /> 完成
                </button>
                <Link
                  aria-label={`让助理协助调整任务：${focus.title}`}
                  to={mobileChatIntentLink(`请先核对任务「${focus.title}」(task_id=${focus.id})的当前状态和关联计划，再帮我评估如何调整后续安排。不要更改永久优先级，也不要未经我确认就应用正式日程。`)}
                  className="inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-medium text-teal-800 hover:bg-teal-50"
                >
                  调整
                </Link>
              </>
            )}
            {focus.kind === "event" && (
              <>
                <Link to="/calendar" aria-label={`查看日程：${focus.title}`} className="inline-flex min-h-12 items-center rounded-xl border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 hover:bg-slate-50">
                  查看日程
                </Link>
                <Link to={mobileEventAdjustmentLink(focus, timezone)} className="inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-medium text-teal-800 hover:bg-teal-50">
                  调整安排
                </Link>
              </>
            )}
          </div>
        </article>
      ) : (
        <section aria-label="当前没有已安排事项" className="border-b border-slate-200 pb-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">现在</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">暂时没有正在进行的安排</h2>
          <p className="mt-1 text-sm text-slate-600">你可以告诉助理今天想完成什么。</p>
          <Link
            to={mobileChatIntentLink("帮我安排今天的任务")}
            className="mobile-on-brand mt-3 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800"
          >
            让助理安排今天
          </Link>
        </section>
      )}

      {otherNow.length > 0 && (
        <section aria-label="同时进行">
          <h3 className="text-base font-semibold text-slate-900">同时进行</h3>
          <div className="mt-1 divide-y divide-slate-200">
            {otherNow.map((item) => <MobileExecutionRow key={`${item.kind}:${item.id}`} item={item} {...listProps} />)}
          </div>
        </section>
      )}

      {remainingNext.length > 0 && (
        <section aria-label="接下来">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-base font-semibold text-slate-900">接下来</h3>
            <span className="text-xs text-slate-600">{remainingNext.length} 项</span>
          </div>
          <div className="mt-1 divide-y divide-slate-200">
            {remainingNext.map((item) => <MobileExecutionRow key={`${item.kind}:${item.id}`} item={item} {...listProps} />)}
          </div>
        </section>
      )}

      {later.length > 0 && (
        <details className="group border-t border-slate-200 pt-3">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-slate-700">
            <span>稍后 · {later.length} 项</span>
            <ChevronDown size={18} className="shrink-0 transition-transform group-open:rotate-180" aria-hidden="true" />
          </summary>
          <div className="mt-1 divide-y divide-slate-200">
            {later.map((item) => <MobileExecutionRow key={`${item.kind}:${item.id}`} item={item} {...listProps} />)}
          </div>
        </details>
      )}
    </section>
  );
}
