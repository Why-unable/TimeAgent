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
import { CalendarDays, CirclePlus, MapPin } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { CalendarEvent } from "../api/events";
import { DayAgendaSheet } from "../components/mobile/day-agenda-sheet";
import { MobileSegmentedControl } from "../components/mobile/mobile-segmented-control";
import { EventEditor } from "../features/events/event-editor";
import { ScheduleWorkspaceTabs } from "../features/workspace/schedule-workspace-tabs";
import { useCancelEvent, useEvents } from "../features/events/hooks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import { formatInUserTimezone, getLocalDateKey } from "../utils/datetime";

const statusLabels = { tentative: "暂定", confirmed: "已确认", cancelled: "已取消" } as const;

type CalendarView = "dayGridMonth" | "timeGridWeek" | "timeGridDay";

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
  const [view, setView] = useState<CalendarView>("dayGridMonth");
  const calendarRef = useRef<CalendarRef | null>(null);
  const [isMobile, setIsMobile] = useState(
    () =>
      typeof window !== "undefined" && typeof window.matchMedia === "function"
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
    setView(info.view.type as CalendarView);
  };

  const changeView = (nextView: CalendarView) => {
    calendarRef.current?.getApi().changeView(nextView);
    setView(nextView);
  };

  const handleEventClick = (info: EventClickInfo) => {
    setSelectedDate(info.event.start ?? undefined);
  };

  const handleDateClick = (info: DateClickInfo) => setSelectedDate(info.date);
  const selectedDateEvents = selectedDate
    ? visibleEvents.filter(
        (event) => getLocalDateKey(event.start_at, timezone) === getLocalDateKey(selectedDate, timezone),
      )
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
    <section className="mx-auto max-w-[1500px]">
      <div className="flex flex-col gap-4 lg:flex-row lg:flex-wrap lg:items-end lg:justify-between">
        {/* Desktop heading — hidden on mobile per §10.1 */}
        <div className="hidden lg:block">
          <div className="mt-2 flex items-center gap-3">
            <CalendarDays className="text-cyan-300" size={31} />
            <h2 className="text-4xl font-semibold">日历</h2>
          </div>
          <p className="mt-4 text-lg text-slate-400">月、周、日视图统一按 {timezone} 展示。</p>
        </div>
      </div>

      <ScheduleWorkspaceTabs />

      {/* Mobile-only intro */}
      <p className="mt-4 text-sm text-slate-500 lg:hidden">
        月、周、日视图按 {timezone} 展示。
      </p>

      {/* Single primary action: full-width on mobile, inline on desktop */}
      <div className="mt-4 lg:mt-6 lg:flex lg:justify-end">
        <button
          type="button"
          onClick={() => setCreateStart(new Date())}
          className="inline-flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-cyan-300 px-6 py-3 text-lg font-semibold text-slate-950 lg:w-auto"
        >
          <CirclePlus size={19} />
          新建日程
        </button>
      </div>

      {/* sr-only heading for accessibility on mobile */}
      <h2 className="sr-only lg:hidden">日历</h2>

      {events.isError && (
        <div role="alert" className="mt-6 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-amber-100">
          无法读取日程，请确认登录状态后重试。
        </div>
      )}

      <div className="mt-4 sm:mt-10 sm:grid sm:gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div
          className={`calendar-shell min-w-0 bg-slate-900 px-2 py-3 sm:rounded-[2rem] sm:border sm:border-white/10 sm:p-5 ${
            isMobile && view === "timeGridWeek" ? "calendar-week-layout" : ""
          }`}
        >
          {events.isPending && <p className="mb-3 text-sm text-slate-400">正在读取当前日历范围…</p>}
          {isMobile && (
            <div className="mb-3">
              <MobileSegmentedControl
                ariaLabel="日历视图"
                value={view}
                onChange={changeView}
                options={[
                  { value: "dayGridMonth", label: "月" },
                  { value: "timeGridWeek", label: "周" },
                  { value: "timeGridDay", label: "日" },
                ]}
              />
            </div>
          )}
          <FullCalendar
            ref={calendarRef}
            plugins={[themePlugin, dayGridPlugin, timeGridPlugin, interactionPlugin]}
            locale={zhCnLocale}
            timeZone={timezone}
            initialView="dayGridMonth"
            headerToolbar={
              isMobile
                ? { left: "prev,next", center: "title", right: "today" }
                : { left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek,timeGridDay" }
            }
            events={calendarEvents}
            datesSet={handleDatesSet}
            eventClick={handleEventClick}
            dateClick={handleDateClick}
            dayCellTopContent={(argument) => argument.dayNumberText.replace(/日$/, "")}
            nowIndicator
            allDaySlot={false}
            fixedWeekCount
            height="auto"
            contentHeight="auto"
            dayMaxEvents={isMobile ? 2 : 3}
            slotDuration="00:30:00"
            slotMinTime="06:00:00"
            slotMaxTime="23:00:00"
          />
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
        <DayAgendaSheet
          date={selectedDate}
          events={selectedDateEvents}
          timezone={timezone}
          locale={locale}
          confirmCancelId={confirmCancelId}
          cancelPending={cancelEvent.isPending}
          cancelError={cancelEvent.error ?? null}
          onClose={() => {
            setSelectedDate(undefined);
            setConfirmCancelId(undefined);
          }}
          onEdit={editEvent}
          onConfirmCancel={confirmCancel}
          onCreateOnThisDay={() => {
            const start = selectedDate;
            setSelectedDate(undefined);
            setCreateStart(start);
          }}
        />
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
