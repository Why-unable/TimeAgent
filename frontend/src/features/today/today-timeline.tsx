import { CalendarClock } from "lucide-react";

import { formatTimeInUserTimezone } from "../../utils/datetime";
import type { TimelineEntry } from "./derive";

/** Vertical today timeline shared by mobile and desktop layouts. */
export function TodayTimeline({
  timeline,
  timezone,
  compact = false,
}: {
  timeline: TimelineEntry[];
  timezone: string;
  compact?: boolean;
}) {
  if (timeline.length === 0) {
    return null;
  }
  return (
    <section
      className={
        compact
          ? "rounded-2xl border border-white/10 bg-slate-900 p-4"
          : "rounded-3xl border border-white/10 bg-slate-900 p-5"
      }
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 font-semibold text-white">
          <CalendarClock size={19} className="text-cyan-300" />
          今日时间线
        </h3>
        <span className="text-xs text-slate-500">{timeline.length} 项安排</span>
      </div>
      <div className="mt-4 space-y-1">
        {timeline.map((item) => (
          <article
            key={`${item.kind}-${item.id}`}
            className="grid grid-cols-[92px_12px_minmax(0,1fr)] gap-3 py-3"
          >
            <time className="text-sm text-slate-400">
              {formatTimeInUserTimezone(item.startAt, timezone)}
              <span className="block text-xs text-slate-600">
                {formatTimeInUserTimezone(item.endAt, timezone)}
              </span>
            </time>
            <span
              className={`mt-1 size-3 rounded-full ${
                item.kind === "event" ? "bg-cyan-400" : "bg-violet-400"
              }`}
            />
            <div>
              <h4 className="font-medium text-slate-100">{item.title}</h4>
              <p className="mt-1 text-xs text-slate-500">
                {item.kind === "event" ? "日程" : "计划任务"} · {item.detail}
              </p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
