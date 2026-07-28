import FullCalendar, {
  type CalendarRef,
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
import { CalendarDays, CirclePlus, MapPin, Pencil, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { CalendarEvent } from "../api/events";
import { EventEditor } from "../features/events/event-editor";
import { ScheduleWorkspaceTabs } from "../features/workspace/schedule-workspace-tabs";
import { useCancelEvent, useEvents } from "../features/events/hooks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import { formatDateKey, formatInUserTimezone, formatTimeInUserTimezone, getLocalDateKey } from "../utils/datetime";

const statusLabels = { tentative: "暂定", confirmed: "已确认", cancelled: "已取消" } as const;

export function CalendarPage() {
  const preference = useCurrentUserPreference();
  const timezone = preference.data?.timezone ?? "Asia/Shanghai";
  const locale = preference.data?.locale ?? "zh-CN";
  const defaultDurationMinutes = preference.data?.default_event_duration_minutes ?? 60;
  const [range, setRange] = useState(() => ({
    startsBefore: new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString(),
    endsAfter: new Date(Date.now() - 45 * 24 * 60 * 60 * 1000).toISOString(),
  }));
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent>();
  const [selectedDate, setSelectedDate] = useState<Date>();
  const [confirmCancelId, setConfirmCancelId] = useState<string>();
  const [createStart, setCreateStart] = useState<Date>();
  const [view, setView] = useState("dayGridMonth");
  const calendarRef = useRef<CalendarRef | null>(null);
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(max-width: 639px)").matches
      : false,
  );
  const events = useEvents(range);
  const cancelEvent = useCancelEvent();

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const media = window.matchMedia("(max-width: 639px)");
    const sync = () => setIsMobile(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  const visibleEvents = useMemo(
    () => (events.data ?? []).filter((event) => event.status !== "cancelled"),
    [events.data],
  );

  const calendarEvents = useMemo<EventInput[]>(
    () =>
      visibleEvents.map((event) => ({
        id: event.id,
        title: event.title,
        start: event.start_at,
        end: event.end_at,
        backgroundColor: event.source === "local" ? "#0891b2" : "#7c3aed",
        borderColor: "transparent",
        textColor: "#f8fafc",
      })),
    [visibleEvents],
  );

  const handleDatesSet = (info: DatesSetInfo) => {
    setRange({ startsBefore: info.end.toISOString(), endsAfter: info.start.toISOString() });
    setView(info.view.type);
  };

  const changeView = (nextView: string) => {
    calendarRef.current?.getApi().changeView(nextView);
  };

  const handleEventClick = (info: EventClickInfo) => {
    setSelectedDate(info.event.start ?? undefined);
  };

  const handleDateClick = (info: DateClickInfo) => setSelectedDate(info.date);
  const selectedDateEvents = selectedDate
    ? visibleEvents.filter((event) => getLocalDateKey(event.start_at, timezone) === getLocalDateKey(selectedDate, timezone))
    : [];

  const editEvent = (event: CalendarEvent) => {
    setSelectedDate(undefined);
    setSelectedEvent(event);
  };

  const confirmCancel = (event: CalendarEvent) => {
    if (confirmCancelId !== event.id) {
      setConfirmCancelId(event.id);
      return;
    }
    cancelEvent.mutate(
      { eventId: event.id, expectedVersion: event.version ?? 1 },
      { onSuccess: () => setConfirmCancelId(undefined) },
    );
  };

  return (
    <section className="-mx-5 flex h-[calc(100dvh-11rem)] flex-col overflow-hidden sm:mx-auto sm:block sm:h-auto sm:max-w-[1500px] sm:overflow-visible">
      <div className="flex flex-wrap items-end justify-between gap-4 px-5 sm:px-0">
        <div>
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

      <div className="px-5 sm:hidden"><ScheduleWorkspaceTabs /></div>

      {events.isError && (
        <div role="alert" className="mx-5 mt-6 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-amber-100 sm:mx-0">
          无法读取日程，请确认登录状态后重试。
        </div>
      )}

      <div className="mt-4 min-h-0 flex-1 px-0 sm:mt-10 sm:grid sm:gap-6 sm:px-0 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className={`calendar-shell flex h-full min-w-0 flex-col bg-slate-900 px-2 py-3 sm:h-auto sm:rounded-[2rem] sm:border sm:border-white/10 sm:p-5 ${isMobile && view === "timeGridWeek" ? "calendar-week-layout" : ""}`}>
          {events.isPending && <p className="mb-3 text-sm text-slate-400">正在读取当前日历范围…</p>}
          {isMobile && (
            <div className="mb-3 grid grid-cols-3 rounded-xl bg-slate-950/70 p-1" aria-label="日历视图">
              {[["dayGridMonth", "月"], ["timeGridWeek", "周"], ["timeGridDay", "日"]].map(([value, label]) => (
                <button key={value} type="button" onClick={() => changeView(value)} className={`rounded-lg py-2 text-sm font-medium transition ${view === value ? "bg-cyan-300 text-slate-950" : "text-slate-400"}`}>{label}</button>
              ))}
            </div>
          )}
          <div className="calendar-scroll min-h-0 flex-1 overflow-auto">
          <FullCalendar
            ref={calendarRef}
            plugins={[themePlugin, dayGridPlugin, timeGridPlugin, interactionPlugin]}
            locale={zhCnLocale}
            timeZone={timezone}
            initialView="dayGridMonth"
            headerToolbar={isMobile
              ? { left: "prev,next", center: "title", right: "today" }
              : { left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek,timeGridDay" }}
            events={calendarEvents}
            datesSet={handleDatesSet}
            eventClick={handleEventClick}
            dateClick={handleDateClick}
            dayCellTopContent={(argument) => argument.dayNumberText.replace(/日$/, "")}
            nowIndicator
            allDaySlot={false}
            height={isMobile ? "100%" : "auto"}
            dayMaxEvents={isMobile ? 2 : 3}
            slotDuration="00:30:00"
            slotMinTime="06:00:00"
            slotMaxTime="23:00:00"
          />
          </div>
        </div>

        <aside className="hidden rounded-2xl border border-white/10 bg-slate-900 p-5 xl:block">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">当前范围</h3>
            <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs text-cyan-200">
              {visibleEvents.length} 项
            </span>
          </div>
          <div className="mt-5 space-y-3">
            {visibleEvents.length === 0 && <p className="text-sm text-slate-500">当前范围暂无日程</p>}
            {visibleEvents.slice(0, 8).map((event) => (
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

      {selectedDate && (
        <div className="fixed inset-0 z-50 flex items-end bg-slate-950/75 p-0 backdrop-blur-sm sm:items-center sm:justify-center sm:p-6" role="dialog" aria-modal="true" aria-label="当日日程">
          <button type="button" aria-label="关闭日程列表" className="absolute inset-0" onClick={() => { setSelectedDate(undefined); setConfirmCancelId(undefined); }} />
          <section className="relative max-h-[82dvh] w-full overflow-y-auto rounded-t-3xl border border-white/10 bg-slate-900 p-5 shadow-2xl sm:max-w-xl sm:rounded-3xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-medium text-cyan-300">当日安排</p>
                <h3 className="mt-1 text-xl font-semibold text-slate-100">{formatDateKey(getLocalDateKey(selectedDate, timezone))}</h3>
              </div>
              <button type="button" aria-label="关闭日程列表" onClick={() => { setSelectedDate(undefined); setConfirmCancelId(undefined); }} className="rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-white"><X size={22} /></button>
            </div>
            <div className="mt-5 space-y-3">
              {selectedDateEvents.length === 0 && <p className="rounded-xl border border-dashed border-white/10 p-5 text-sm text-slate-500">这一天还没有日程。</p>}
              {selectedDateEvents.map((event) => (
                <article key={event.id} className="rounded-2xl border border-white/10 bg-slate-950/55 p-4">
                  <div className="flex gap-3">
                    <span className="mt-1 size-2 shrink-0 rounded-full bg-cyan-300" />
                    <div className="min-w-0 flex-1">
                      <h4 className="font-medium text-slate-100">{event.title}</h4>
                      <p className="mt-1 text-sm text-slate-400">{formatTimeInUserTimezone(event.start_at, timezone, locale)} — {formatTimeInUserTimezone(event.end_at, timezone, locale)}</p>
                      {event.location && <p className="mt-1 flex items-center gap-1 text-sm text-slate-500"><MapPin size={14} />{event.location}</p>}
                    </div>
                  </div>
                  <div className="mt-4 flex justify-end gap-2">
                    <button type="button" onClick={() => editEvent(event)} className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-200 hover:bg-white/5"><Pencil size={15} />修改</button>
                    <button type="button" disabled={cancelEvent.isPending} onClick={() => confirmCancel(event)} className={`inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm disabled:opacity-50 ${confirmCancelId === event.id ? "bg-red-400 text-slate-950" : "border border-red-300/30 text-red-200 hover:bg-red-300/10"}`}><Trash2 size={15} />{confirmCancelId === event.id ? "确认删除" : "删除"}</button>
                  </div>
                </article>
              ))}
              {cancelEvent.error && <p role="alert" className="rounded-xl border border-red-300/30 bg-red-300/10 p-3 text-sm text-red-100">{cancelEvent.error.message}</p>}
            </div>
            <button type="button" onClick={() => { setSelectedDate(undefined); setCreateStart(selectedDate); }} className="mt-5 w-full rounded-xl border border-cyan-300/30 px-4 py-3 text-sm font-medium text-cyan-200 hover:bg-cyan-300/10">在这一天新建日程</button>
          </section>
        </div>
      )}

      {createStart && (
        <EventEditor
          key={`create-${createStart.toISOString()}`}
          initialStart={createStart}
          timezone={timezone}
          defaultDurationMinutes={defaultDurationMinutes}
          onClose={() => setCreateStart(undefined)}
        />
      )}
      {selectedEvent && (
        <EventEditor
          key={`${selectedEvent.id}-${selectedEvent.version}`}
          event={selectedEvent}
          timezone={timezone}
          defaultDurationMinutes={defaultDurationMinutes}
          onClose={() => setSelectedEvent(undefined)}
        />
      )}
    </section>
  );
}
