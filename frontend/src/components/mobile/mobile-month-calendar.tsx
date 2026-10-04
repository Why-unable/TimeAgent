import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import { addDaysToDateKey, dateKeyAsUtcDate } from "../../utils/date-key";

function monthStart(dateKey: string) {
  return `${dateKey.slice(0, 7)}-01`;
}

function moveMonth(dateKey: string, offset: number) {
  const [year, month] = dateKey.slice(0, 7).split("-").map(Number);
  const target = new Date(0);
  target.setUTCFullYear(year, month - 1 + offset, 1);
  target.setUTCHours(0, 0, 0, 0);
  return target.toISOString().slice(0, 10);
}

function dateAccessibleName(dateKey: string, locale: string, todayKey: string, eventCount: number) {
  const label = new Intl.DateTimeFormat(locale, {
    year: "numeric", month: "long", day: "numeric", weekday: "long", timeZone: "UTC",
  }).format(dateKeyAsUtcDate(dateKey));
  return `${label}${dateKey === todayKey ? "，今天" : ""}，${eventCount} 项日程`;
}

export function MobileMonthCalendar({
  todayKey,
  selectedDateKey,
  locale,
  eventCounts,
  onSelectDate,
  onMonthChange,
}: {
  todayKey: string;
  selectedDateKey: string;
  locale: string;
  eventCounts: Record<string, number>;
  onSelectDate: (dateKey: string) => void;
  onMonthChange: (startDateKey: string, endDateKeyExclusive: string) => void;
}) {
  const [displayedMonth, setDisplayedMonth] = useState(() => monthStart(selectedDateKey));
  const [focusedDateKey, setFocusedDateKey] = useState(selectedDateKey.slice(0, 7) === displayedMonth
    ? selectedDateKey
    : displayedMonth);
  const pendingFocusDateKey = useRef<string | undefined>(undefined);
  const buttonRefs = useRef(new Map<string, HTMLButtonElement>());
  const cells = useMemo(() => {
    const firstDay = dateKeyAsUtcDate(displayedMonth);
    const mondayOffset = (firstDay.getUTCDay() + 6) % 7;
    const firstCell = addDaysToDateKey(displayedMonth, -mondayOffset);
    return Array.from({ length: 42 }, (_, index) => addDaysToDateKey(firstCell, index));
  }, [displayedMonth]);

  useEffect(() => {
    onMonthChange(cells[0], addDaysToDateKey(cells.at(-1) as string, 1));
  }, [cells, onMonthChange]);

  useEffect(() => {
    if (selectedDateKey.slice(0, 7) === displayedMonth) setFocusedDateKey(selectedDateKey);
  }, [displayedMonth, selectedDateKey]);

  useLayoutEffect(() => {
    const target = pendingFocusDateKey.current;
    if (!target) return;
    buttonRefs.current.get(target)?.focus();
    pendingFocusDateKey.current = undefined;
  }, [cells, focusedDateKey]);

  const weekdayLabels = Array.from({ length: 7 }, (_, index) => {
    const monday = dateKeyAsUtcDate("2026-10-05");
    monday.setUTCDate(monday.getUTCDate() + index);
    return new Intl.DateTimeFormat(locale, { weekday: "short", timeZone: "UTC" }).format(monday);
  });

  const setMonth = (nextMonth: string) => {
    setDisplayedMonth(monthStart(nextMonth));
    setFocusedDateKey(monthStart(nextMonth));
  };

  const focusDate = (dateKey: string) => {
    if (dateKey.slice(0, 7) !== displayedMonth) setDisplayedMonth(monthStart(dateKey));
    setFocusedDateKey(dateKey);
    pendingFocusDateKey.current = dateKey;
  };

  const handleDateKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>, dateKey: string) => {
    let nextDate: string | undefined;
    if (event.key === "ArrowLeft") nextDate = addDaysToDateKey(dateKey, -1);
    else if (event.key === "ArrowRight") nextDate = addDaysToDateKey(dateKey, 1);
    else if (event.key === "ArrowUp") nextDate = addDaysToDateKey(dateKey, -7);
    else if (event.key === "ArrowDown") nextDate = addDaysToDateKey(dateKey, 7);
    else if (event.key === "Home") nextDate = addDaysToDateKey(dateKey, -((dateKeyAsUtcDate(dateKey).getUTCDay() + 6) % 7));
    else if (event.key === "End") nextDate = addDaysToDateKey(dateKey, 6 - ((dateKeyAsUtcDate(dateKey).getUTCDay() + 6) % 7));
    else if (event.key === "PageUp") nextDate = moveMonth(dateKey, -1);
    else if (event.key === "PageDown") nextDate = moveMonth(dateKey, 1);
    if (nextDate) {
      event.preventDefault();
      focusDate(nextDate);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelectDate(dateKey);
    }
  };

  return (
    <section aria-label="日历日期选择" className="mobile-month-calendar rounded-2xl border border-slate-200 bg-white p-3 shadow-sm sm:p-5">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-label="上个月"
          onClick={() => setMonth(moveMonth(displayedMonth, -1))}
          className="grid min-h-11 min-w-11 place-items-center rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
        ><ChevronLeft size={20} /></button>
        <h3 className="text-base font-semibold text-slate-900">
          {new Intl.DateTimeFormat(locale, { year: "numeric", month: "long", timeZone: "UTC" })
            .format(dateKeyAsUtcDate(displayedMonth))}
        </h3>
        <button
          type="button"
          aria-label="下个月"
          onClick={() => setMonth(moveMonth(displayedMonth, 1))}
          className="grid min-h-11 min-w-11 place-items-center rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
        ><ChevronRight size={20} /></button>
        <button
          type="button"
          onClick={() => {
            setMonth(todayKey);
            onSelectDate(todayKey);
          }}
          className="min-h-11 shrink-0 rounded-lg px-2 text-sm font-semibold text-teal-800 hover:bg-teal-50"
        >今天</button>
      </div>
      <div className="mt-4 px-1 sm:px-0">
        <div role="grid" aria-label="选择日期" className="grid grid-cols-7">
          <div role="row" className="contents">
            {weekdayLabels.map((label, index) => (
              <div key={`${label}-${index}`} role="columnheader" className="pb-2 text-center text-xs font-medium text-slate-600">
                {label}
              </div>
            ))}
          </div>
          {Array.from({ length: 6 }, (_, weekIndex) => (
            <div key={weekIndex} role="row" className="contents">
              {cells.slice(weekIndex * 7, weekIndex * 7 + 7).map((dateKey) => {
                const inMonth = dateKey.slice(0, 7) === displayedMonth;
                const selected = dateKey === selectedDateKey;
                const focused = dateKey === focusedDateKey;
                const count = eventCounts[dateKey] ?? 0;
                return (
                  <div key={dateKey} role="gridcell" aria-selected={selected} className="min-w-0">
                    <button
                      ref={(element) => {
                        if (element) buttonRefs.current.set(dateKey, element);
                        else buttonRefs.current.delete(dateKey);
                      }}
                      type="button"
                      tabIndex={focused ? 0 : -1}
                      aria-label={dateAccessibleName(dateKey, locale, todayKey, count)}
                      aria-pressed={selected}
                      onClick={() => onSelectDate(dateKey)}
                      onKeyDown={(event) => handleDateKeyDown(event, dateKey)}
                      className={`flex min-h-12 w-full flex-col items-center justify-center rounded-xl border text-sm transition ${selected
                        ? "border-teal-800 bg-teal-800 font-semibold text-white ring-2 ring-teal-800 ring-offset-1 mobile-on-brand"
                        : dateKey === todayKey
                          ? "border-teal-700 bg-white font-semibold text-teal-900"
                          : "border-transparent bg-white text-slate-800 hover:bg-slate-50"
                      } ${inMonth ? "" : "opacity-50"}`}
                    >
                      <span>{Number(dateKey.slice(-2))}</span>
                      {count > 0 && <span aria-hidden="true" className={`mt-0.5 size-1.5 rounded-full ${selected ? "bg-white" : "bg-teal-700"}`} />}
                      {count === 0 && <span aria-hidden="true" className="mt-0.5 size-1.5" />}
                    </button>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
