import { MapPin, Pencil, Trash2, X } from "lucide-react";

import type { CalendarEvent } from "../../api/events";
import { formatDateKey, formatTimeInUserTimezone, getLocalDateKey } from "../../utils/datetime";

/** Bottom-sheet on mobile / centred dialog on desktop that lists a single day's
 * events and offers edit + delete (with a two-tap confirm) + new-in-this-day. */
export function DayAgendaSheet({
  date,
  events,
  timezone,
  locale,
  confirmCancelId,
  cancelPending,
  cancelError,
  onClose,
  onEdit,
  onConfirmCancel,
  onCreateOnThisDay,
}: {
  date: Date;
  events: CalendarEvent[];
  timezone: string;
  locale?: string;
  confirmCancelId: string | undefined;
  cancelPending: boolean;
  cancelError: Error | null;
  onClose: () => void;
  onEdit: (event: CalendarEvent) => void;
  onConfirmCancel: (event: CalendarEvent) => void;
  onCreateOnThisDay: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end bg-slate-950/75 p-0 backdrop-blur-sm sm:items-center sm:justify-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="当日日程"
    >
      <button
        type="button"
        aria-label="关闭日程列表"
        className="absolute inset-0"
        onClick={onClose}
      />
      <section className="relative max-h-[82dvh] w-full overflow-y-auto rounded-t-3xl border border-white/10 bg-slate-900 p-5 shadow-2xl sm:max-w-xl sm:rounded-3xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium text-cyan-300">当日安排</p>
            <h3 className="mt-1 text-xl font-semibold text-slate-100">
              {formatDateKey(getLocalDateKey(date, timezone))}
            </h3>
          </div>
          <button
            type="button"
            aria-label="关闭日程列表"
            onClick={onClose}
            className="rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-white"
          >
            <X size={22} />
          </button>
        </div>
        <div className="mt-5 space-y-3">
          {events.length === 0 && (
            <p className="rounded-xl border border-dashed border-white/10 p-5 text-sm text-slate-500">
              这一天还没有日程。
            </p>
          )}
          {events.map((event) => {
            const hasEnded = new Date(event.end_at).getTime() <= Date.now();
            return (
              <article
              key={event.id}
              className="rounded-2xl border border-white/10 bg-slate-950/55 p-4"
              >
              <div className="flex gap-3">
                <span className="mt-1 size-2 shrink-0 rounded-full bg-cyan-300" />
                <div className="min-w-0 flex-1">
                  <h4 className="font-medium text-slate-100">{event.title}</h4>
                  <p className="mt-1 text-sm text-slate-400">
                    {formatTimeInUserTimezone(event.start_at, timezone, locale)} —{" "}
                    {formatTimeInUserTimezone(event.end_at, timezone, locale)}
                  </p>
                  {event.location && (
                    <p className="mt-1 flex items-center gap-1 text-sm text-slate-500">
                      <MapPin size={14} />
                      {event.location}
                    </p>
                  )}
                </div>
              </div>
                {hasEnded ? (
                  <p className="mt-4 text-right text-xs text-slate-500">已结束，仅可查看</p>
                ) : (
                  <div className="mt-4 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => onEdit(event)}
                      className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-200 hover:bg-white/5"
                    >
                      <Pencil size={15} />
                      修改
                    </button>
                    <button
                      type="button"
                      disabled={cancelPending}
                      onClick={() => onConfirmCancel(event)}
                      className={`inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm disabled:opacity-50 ${
                        confirmCancelId === event.id
                          ? "bg-red-400 text-slate-950"
                          : "border border-red-300/30 text-red-200 hover:bg-red-300/10"
                      }`}
                    >
                      <Trash2 size={15} />
                      {confirmCancelId === event.id ? "确认删除" : "删除"}
                    </button>
                  </div>
                )}
              </article>
            );
          })}
          {cancelError && (
            <p
              role="alert"
              className="rounded-xl border border-red-300/30 bg-red-300/10 p-3 text-sm text-red-100"
            >
              {cancelError.message}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onCreateOnThisDay}
          className="mt-5 w-full rounded-xl border border-cyan-300/30 px-4 py-3 text-sm font-medium text-cyan-200 hover:bg-cyan-300/10"
        >
          在这一天新建日程
        </button>
      </section>
    </div>
  );
}
