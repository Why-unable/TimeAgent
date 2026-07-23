import FullCalendar, {
  type DateClickInfo,
  type DatesSetInfo,
  type EventClickInfo,
  type EventInput,
} from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/react/daygrid";
import interactionPlugin from "@fullcalendar/react/interaction";
import zhCnLocale from "@fullcalendar/react/locales/zh-cn";
import themePlugin from "@fullcalendar/react/themes/monarch";
import timeGridPlugin from "@fullcalendar/react/timegrid";
import { CalendarDays, CirclePlus, MapPin } from "lucide-react";
import { useMemo, useState } from "react";

import type { CalendarEvent } from "../api/events";
import { EventEditor } from "../features/events/event-editor";
import { useEvents } from "../features/events/hooks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import { formatInUserTimezone } from "../utils/datetime";

const statusLabels = { tentative: "暂定", confirmed: "已确认", cancelled: "已取消" } as const;

export function CalendarPage() {
  const preference = useCurrentUserPreference();
  const timezone = preference.data?.timezone ?? "Asia/Shanghai";
  const locale = preference.data?.locale ?? "zh-CN";
  const [range, setRange] = useState(() => ({
    startsBefore: new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString(),
    endsAfter: new Date(Date.now() - 45 * 24 * 60 * 60 * 1000).toISOString(),
  }));
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent>();
  const [createStart, setCreateStart] = useState<Date>();
  const events = useEvents(range);

  const calendarEvents = useMemo<EventInput[]>(
    () =>
      (events.data ?? []).map((event) => ({
        id: event.id,
        title: event.title,
        start: event.start_at,
        end: event.end_at,
        backgroundColor:
          event.status === "cancelled"
            ? "#475569"
            : event.source === "local"
              ? "#0891b2"
              : "#7c3aed",
        borderColor: "transparent",
        textColor: "#f8fafc",
        classNames: event.status === "cancelled" ? ["event-cancelled"] : [],
      })),
    [events.data],
  );

  const handleDatesSet = (info: DatesSetInfo) => {
    setRange({ startsBefore: info.end.toISOString(), endsAfter: info.start.toISOString() });
  };

  const handleEventClick = (info: EventClickInfo) => {
    setSelectedEvent(events.data?.find((event) => event.id === info.event.id));
  };

  const handleDateClick = (info: DateClickInfo) => setCreateStart(info.date);

  return (
    <section className="mx-auto max-w-[1500px]">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="hidden text-sm font-medium text-cyan-300 lg:block">Phase 3 · 结构化事务</p>
          <div className="mt-2 flex items-center gap-3">
            <CalendarDays className="text-cyan-300" size={31} />
            <h2 className="text-4xl font-semibold">日历</h2>
          </div>
          <p className="mt-4 text-lg text-slate-400">月、周、日视图统一按 {timezone} 展示。</p>
        </div>
        <button
          type="button"
          onClick={() => setCreateStart(new Date())}
          className="inline-flex min-h-14 items-center gap-2 rounded-2xl bg-cyan-300 px-6 py-3 text-lg font-semibold text-slate-950"
        >
          <CirclePlus size={19} />
          新建日程
        </button>
      </div>

      {events.isError && (
        <div role="alert" className="mt-6 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-amber-100">
          无法读取日程，请确认登录状态后重试。
        </div>
      )}

      <div className="mt-10 grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="calendar-shell min-w-0 rounded-[2rem] border border-white/10 bg-slate-900 p-3 sm:p-5">
          {events.isPending && <p className="mb-3 text-sm text-slate-400">正在读取当前日历范围…</p>}
          <FullCalendar
            plugins={[themePlugin, dayGridPlugin, timeGridPlugin, interactionPlugin]}
            locale={zhCnLocale}
            timeZone={timezone}
            initialView="dayGridMonth"
            headerToolbar={{
              left: "prev,next today",
              center: "title",
              right: "dayGridMonth,timeGridWeek,timeGridDay",
            }}
            events={calendarEvents}
            datesSet={handleDatesSet}
            eventClick={handleEventClick}
            dateClick={handleDateClick}
            nowIndicator
            allDaySlot={false}
            height="auto"
            dayMaxEvents={3}
            slotMinTime="06:00:00"
            slotMaxTime="23:00:00"
          />
        </div>

        <aside className="rounded-2xl border border-white/10 bg-slate-900 p-5">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">当前范围</h3>
            <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs text-cyan-200">
              {events.data?.length ?? 0} 项
            </span>
          </div>
          <div className="mt-5 space-y-3">
            {events.data?.length === 0 && <p className="text-sm text-slate-500">当前范围暂无日程</p>}
            {events.data?.slice(0, 8).map((event) => (
              <button
                type="button"
                key={event.id}
                onClick={() => setSelectedEvent(event)}
                className="w-full rounded-xl border border-white/5 bg-slate-950/70 p-4 text-left hover:border-cyan-300/30"
              >
                <div className="flex items-start justify-between gap-3">
                  <span className="font-medium text-slate-100">{event.title}</span>
                  <span className="shrink-0 text-[11px] text-slate-500">
                    {statusLabels[event.status ?? "confirmed"]}
                  </span>
                </div>
                <p className="mt-2 text-xs text-slate-400">
                  {formatInUserTimezone(event.start_at, timezone, locale)}
                </p>
                {event.location && (
                  <p className="mt-2 flex items-center gap-1 text-xs text-slate-500">
                    <MapPin size={12} /> {event.location}
                  </p>
                )}
              </button>
            ))}
          </div>
          <div className="mt-5 flex gap-4 border-t border-white/10 pt-4 text-xs text-slate-400">
            <span><i className="mr-1 inline-block size-2 rounded-full bg-cyan-600" />本地</span>
            <span><i className="mr-1 inline-block size-2 rounded-full bg-violet-600" />外部</span>
          </div>
        </aside>
      </div>

      {createStart && (
        <EventEditor
          key={`create-${createStart.toISOString()}`}
          initialStart={createStart}
          timezone={timezone}
          onClose={() => setCreateStart(undefined)}
        />
      )}
      {selectedEvent && (
        <EventEditor
          key={`${selectedEvent.id}-${selectedEvent.version}`}
          event={selectedEvent}
          timezone={timezone}
          onClose={() => setSelectedEvent(undefined)}
        />
      )}
    </section>
  );
}
