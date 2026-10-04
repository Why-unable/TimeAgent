import { MapPin, Pencil, Trash2 } from "lucide-react";

import type { CalendarEvent } from "../../api/events";
import { formatDateKey, formatTimeInUserTimezone } from "../../utils/datetime";
import { Drawer } from "../overlay/drawer";

/** Bottom-sheet on mobile / centred dialog on desktop that lists a single day's
 * events and offers edit + delete (with a two-tap confirm) + new-in-this-day. */
export function DayAgendaSheet({
  dateKey,
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
  dateKey: string;
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
    <Drawer title={formatDateKey(dateKey)} description="当日安排" onClose={onClose}>
        <div className="mt-5 space-y-3">
          {events.length === 0 && (
            <p className="rounded-xl border border-dashed border-white/10 p-5 text-sm text-slate-500">
              这一天还没有日程。
            </p>
          )}
          {events.map((event) => {
            const hasEnded = new Date(event.end_at).getTime() <= Date.now();
            return (
              <article key={event.id} className="border-b border-slate-200 py-4 first:pt-0">
              <div className="flex gap-3">
                <span className="mt-1 size-2 shrink-0 rounded-full bg-teal-700" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <h4 className="font-medium text-slate-900">{event.title}</h4>
                  <p className="mt-1 text-sm text-slate-700">
                    {formatTimeInUserTimezone(event.start_at, timezone, locale)} —{" "}
                    {formatTimeInUserTimezone(event.end_at, timezone, locale)}
                  </p>
                  {event.location && (
                    <p className="mt-1 flex items-center gap-1 text-sm text-slate-700">
                      <MapPin size={14} />
                      {event.location}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-slate-600">
                    {event.source === "local" ? "本地日程" : "外部日历"}
                  </p>
                </div>
              </div>
                {hasEnded ? (
                  <p className="mt-4 text-right text-xs text-slate-600">已结束，仅可查看</p>
                ) : (
                  <div className="mt-4 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => onEdit(event)}
                      className="inline-flex min-h-11 items-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
                    >
                      <Pencil size={15} />
                      修改
                    </button>
                    <button
                      type="button"
                      disabled={cancelPending}
                      onClick={() => onConfirmCancel(event)}
                      className={`inline-flex min-h-11 items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-50 ${
                        confirmCancelId === event.id
                          ? "bg-red-700 text-white"
                          : "border border-red-300 text-red-800 hover:bg-red-50"
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
            <p role="alert" className="rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-900">
              {cancelError.message}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onCreateOnThisDay}
          className="mt-5 min-h-12 w-full rounded-xl bg-teal-700 px-4 py-3 text-sm font-semibold text-white hover:bg-teal-800 mobile-on-brand"
        >
          在这一天新建日程
        </button>
    </Drawer>
  );
}
