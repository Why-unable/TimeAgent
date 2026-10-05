import { CalendarDays, ChevronLeft, ChevronRight, Clock3, ListTodo, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useEvents } from "../features/events/hooks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import { useTasks } from "../features/tasks/hooks";
import { formatDateKey, formatInUserTimezone, formatTimeInUserTimezone, getLocalDateKey } from "../utils/datetime";
import { addDaysToDateKey, dateKeyAsUtcDate, expandedUtcDateRange, mondayOfDateKey } from "../utils/date-key";
import { PageHeader } from "../components/ui/primitives";

type AgendaItem = {
  id: string;
  kind: "event" | "task";
  title: string;
  startAt: string;
  endAt: string;
  location?: string;
  dueAt?: string | null;
};

function shortWeekday(dateKey: string, locale: string) {
  return new Intl.DateTimeFormat(locale, { weekday: "short", timeZone: "UTC" })
    .format(dateKeyAsUtcDate(dateKey));
}

function monthDay(dateKey: string, locale: string) {
  return new Intl.DateTimeFormat(locale, { month: "short", day: "numeric", timeZone: "UTC" })
    .format(dateKeyAsUtcDate(dateKey));
}

export function ScheduleHubPage() {
  const preference = useCurrentUserPreference();
  const timezone = preference.data?.timezone ?? "Asia/Shanghai";
  const locale = preference.data?.locale ?? "zh-CN";
  const [todayKey, setTodayKey] = useState(() => getLocalDateKey(new Date(), timezone));
  const [selectedDateKey, setSelectedDateKey] = useState(todayKey);
  const [weekStartKey, setWeekStartKey] = useState(() => mondayOfDateKey(todayKey));
  const weekEndKey = addDaysToDateKey(weekStartKey, 7);
  const eventRange = useMemo(
    () => expandedUtcDateRange(weekStartKey, weekEndKey),
    [weekEndKey, weekStartKey],
  );
  const events = useEvents({
    startsBefore: eventRange.startsBefore,
    endsAfter: eventRange.endsAfter,
  });
  const tasks = useTasks();

  useEffect(() => {
    const localToday = getLocalDateKey(new Date(), timezone);
    setTodayKey(localToday);
    setSelectedDateKey(localToday);
    setWeekStartKey(mondayOfDateKey(localToday));
  }, [timezone]);

  const dates = Array.from({ length: 7 }, (_, index) => addDaysToDateKey(weekStartKey, index));
  const selectedEvents = (events.data ?? []).filter(
    (event) => event.status !== "cancelled" && getLocalDateKey(event.start_at, timezone) === selectedDateKey,
  );
  const eventsByDate = events.data ?? [];
  const activeTasks = (tasks.data ?? []).filter(
    (task) => task.status === "pending" || task.status === "in_progress",
  );
  const selectedPlannedTasks = activeTasks.filter(
    (task) => task.planned_start_at && getLocalDateKey(task.planned_start_at, timezone) === selectedDateKey,
  );
  const unplannedTasks = activeTasks.filter((task) => !task.planned_start_at);
  const agendaItems = useMemo<AgendaItem[]>(() => [
    ...selectedEvents.map((event) => ({
      id: event.id,
      kind: "event" as const,
      title: event.title,
      startAt: event.start_at,
      endAt: event.end_at,
      location: event.location || undefined,
    })),
    ...selectedPlannedTasks.map((task) => ({
      id: task.id,
      kind: "task" as const,
      title: task.title,
      startAt: task.planned_start_at as string,
      endAt: task.planned_end_at ?? task.planned_start_at as string,
      dueAt: task.due_at,
    })),
  ].sort((left, right) => Date.parse(left.startAt) - Date.parse(right.startAt)), [selectedEvents, selectedPlannedTasks]);

  const moveWeek = (offset: number) => {
    const nextSelectedDate = addDaysToDateKey(selectedDateKey, offset * 7);
    setWeekStartKey(addDaysToDateKey(weekStartKey, offset * 7));
    setSelectedDateKey(nextSelectedDate);
  };
  const selectedDateQuery = new URLSearchParams({ date: selectedDateKey }).toString();

  return (
    <section className="mx-auto max-w-4xl space-y-6 max-[360px]:space-y-4">
      <PageHeader
        className="mt-2 lg:mt-6"
        icon={<CalendarDays className="text-teal-700" size={25} />}
        title="计划"
        description="查看每天的日程与已计划任务，再决定下一步。"
      />

      <section aria-label="选择日期" data-surface="none" className="min-w-0">
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            aria-label="上一周"
            onClick={() => moveWeek(-1)}
            className="grid min-h-11 min-w-11 place-items-center rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
          >
            <ChevronLeft size={20} />
          </button>
          <p className="min-w-0 text-center text-sm font-semibold text-slate-800">
            {monthDay(weekStartKey, locale)} – {monthDay(addDaysToDateKey(weekStartKey, 6), locale)}
          </p>
          <button
            type="button"
            aria-label="下一周"
            onClick={() => moveWeek(1)}
            className="grid min-h-11 min-w-11 place-items-center rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
          >
            <ChevronRight size={20} />
          </button>
        </div>
        <div className="plan-date-rail mt-3 grid w-full min-w-0 grid-cols-7 gap-0.5" role="group" aria-label="本周日期">
          {dates.map((dateKey) => {
            const selected = dateKey === selectedDateKey;
            const dateEvents = eventsByDate.filter(
              (event) => event.status !== "cancelled" && getLocalDateKey(event.start_at, timezone) === dateKey,
            );
            const datePlannedTasks = activeTasks.filter(
              (task) => task.planned_start_at && getLocalDateKey(task.planned_start_at, timezone) === dateKey,
            );
            const count = dateEvents.length + datePlannedTasks.length;
            return (
              <button
                key={dateKey}
                type="button"
                aria-pressed={selected}
                aria-label={`${formatDateKey(dateKey, locale)}${dateKey === todayKey ? "，今天" : ""}，${count} 项安排`}
                onClick={() => setSelectedDateKey(dateKey)}
                className={`flex min-h-12 min-w-0 flex-col items-center justify-center rounded-lg px-0.5 text-xs transition ${selected
                  ? "bg-teal-800 font-bold text-white mobile-on-brand"
                  : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                <span>{shortWeekday(dateKey, locale)}</span>
                <span className="mt-0.5 text-sm">{Number(dateKey.slice(-2))}</span>
                <span className="sr-only">{count ? `${count} 项安排` : "无安排"}</span>
              </button>
            );
          })}
        </div>
        <p className="plan-date-scroll-hint mt-1 text-right text-xs text-slate-500">左右滑动可查看其余日期</p>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
          <p className="text-sm font-medium text-slate-700" aria-live="polite">{formatDateKey(selectedDateKey, locale)}</p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setWeekStartKey(mondayOfDateKey(todayKey));
                setSelectedDateKey(todayKey);
              }}
              className="min-h-11 rounded-lg px-3 text-sm font-medium text-teal-800 hover:bg-teal-50"
            >
              本周
            </button>
            <Link
              to={`/calendar?${selectedDateQuery}`}
              className="inline-flex min-h-11 items-center gap-1 rounded-lg px-3 text-sm font-semibold text-teal-800 hover:bg-teal-50"
            >
              <CalendarDays size={16} /> 日历
            </Link>
          </div>
        </div>
      </section>

      <section aria-labelledby="schedule-day-heading" data-surface="none" className="border-t border-slate-200 pt-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="schedule-day-heading" className="text-lg font-semibold text-slate-900">当天安排</h2>
            <p className="mt-1 text-sm text-slate-600">日程和计划任务按 {timezone} 显示</p>
          </div>
          <Link
            to={`/calendar?${selectedDateQuery}`}
            className="inline-flex min-h-11 shrink-0 items-center gap-1 rounded-lg px-2 text-sm font-medium text-teal-800 hover:bg-teal-50"
          >
            查看日历
          </Link>
        </div>
        {events.isPending && <p className="mt-4 text-sm text-slate-600">正在读取当天日程…</p>}
        {events.isError && (
          <div role="alert" className="mt-4 border-l-2 border-amber-600 py-2 pl-3 text-sm text-amber-950">
            <p>当天日程暂时无法读取。</p>
            <button type="button" onClick={() => void events.refetch()} className="mt-2 min-h-11 font-semibold text-teal-800">重试</button>
          </div>
        )}
        {tasks.isPending && <p className="mt-3 text-sm text-slate-600">正在读取已计划任务…</p>}
        {tasks.isError && (
          <div role="alert" className="mt-3 border-l-2 border-amber-600 py-2 pl-3 text-sm text-amber-950">
            <p>已计划任务暂时无法读取。</p>
            <button type="button" onClick={() => void tasks.refetch()} className="mt-2 min-h-11 font-semibold text-teal-800">重试</button>
          </div>
        )}
        {!events.isPending && !events.isError && !tasks.isPending && !tasks.isError && agendaItems.length === 0 && (
          <p className="mt-4 text-sm text-slate-600">这一天还没有日程或计划任务。</p>
        )}
        {!events.isError && !tasks.isError && agendaItems.length > 0 && (
          <ul className="mt-3 divide-y divide-slate-100">
            {agendaItems.slice(0, 3).map((item) => (
              <li key={`${item.kind}-${item.id}`}>
                <Link
                  to={item.kind === "event" ? `/calendar?${selectedDateQuery}` : "/tasks"}
                  className="flex min-h-14 items-start gap-3 py-3 text-left hover:bg-slate-50"
                >
                  <span className="mt-0.5 inline-flex min-w-[4.25rem] items-center gap-1 text-sm font-semibold tabular-nums text-slate-800">
                    <Clock3 size={14} className="shrink-0 text-teal-800" />
                    {formatTimeInUserTimezone(item.startAt, timezone, locale)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block break-words text-sm font-medium text-slate-900">{item.title}</span>
                    <span className="mt-1 block text-xs text-slate-600">
                      {item.kind === "event" ? "日程" : "计划任务"}
                      {item.location ? ` · ${item.location}` : ""}
                      {item.dueAt ? ` · 截止 ${formatInUserTimezone(item.dueAt, timezone, locale)}` : ""}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        {agendaItems.length > 3 && (
          <Link to={`/calendar?${selectedDateQuery}`} className="mt-2 inline-flex min-h-11 items-center px-2 text-sm font-semibold text-teal-800">
            查看全部 {agendaItems.length} 项安排
          </Link>
        )}
      </section>

      <section aria-labelledby="unplanned-tasks-heading" data-surface="none" className="border-t border-slate-200 pt-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <ListTodo size={20} className="shrink-0 text-teal-800" />
            <h2 id="unplanned-tasks-heading" className="text-lg font-semibold text-slate-900">待安排任务</h2>
            {!tasks.isPending && !tasks.isError && <span className="text-sm text-slate-600">{unplannedTasks.length} 项</span>}
          </div>
          <Link to="/tasks" className="inline-flex min-h-11 shrink-0 items-center px-2 text-sm font-semibold text-teal-800">全部任务</Link>
        </div>
        {tasks.isPending && <p className="mt-3 text-sm text-slate-600">正在读取任务…</p>}
        {tasks.isError && <p role="alert" className="mt-3 text-sm text-amber-950">任务暂时无法读取。</p>}
        {!tasks.isPending && !tasks.isError && unplannedTasks.length === 0 && (
          <p className="mt-3 text-sm text-slate-700">当前没有待安排任务。</p>
        )}
        {!tasks.isError && unplannedTasks.length > 0 && (
          <ul className="mt-2 divide-y divide-slate-100">
            {unplannedTasks.slice(0, 3).map((task) => (
              <li key={task.id}>
                <Link to="/tasks" className="flex min-h-14 items-start justify-between gap-3 py-3">
                  <span className="min-w-0 break-words text-sm font-medium text-slate-900">{task.title}</span>
                  <span className="shrink-0 text-right text-xs text-slate-600">
                    {task.due_at ? `截止 ${formatInUserTimezone(task.due_at, timezone, locale)}` : "未设截止"}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="pb-4">
        <Link to="/planning" className="ui-button ui-button-primary inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-teal-700 px-5 py-3 text-base font-semibold text-white hover:bg-teal-800">
          <Sparkles size={19} />让助理起草安排
        </Link>
        <p className="mt-2 text-center text-xs text-slate-600">计划会先作为草案供你检查，不会自动应用。</p>
      </section>
    </section>
  );
}
