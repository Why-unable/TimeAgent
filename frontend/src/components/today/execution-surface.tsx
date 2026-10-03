import { CheckCircle2, Play } from "lucide-react";
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
