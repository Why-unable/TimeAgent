import { formatInTimeZone } from "date-fns-tz";

const API_TIMEZONE_PATTERN = /(Z|[+-]\d{2}:\d{2})$/;

export function parseApiDateTime(value: string): Date {
  if (!API_TIMEZONE_PATTERN.test(value)) {
    throw new Error("API datetime must include an explicit UTC offset");
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error("Invalid API datetime");
  }
  return parsed;
}

export function formatInUserTimezone(
  value: string | Date,
  timezone: string,
  locale = "zh-CN",
): string {
  const date = typeof value === "string" ? parseApiDateTime(value) : value;
  return new Intl.DateTimeFormat(locale, {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

export function formatTimeInUserTimezone(
  value: string | Date,
  timezone: string,
  locale = "zh-CN",
): string {
  const date = typeof value === "string" ? parseApiDateTime(value) : value;
  return new Intl.DateTimeFormat(locale, {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

export function formatDateKey(dateKey: string, locale = "zh-CN"): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateKey);
  if (!match) throw new Error("Date key must use YYYY-MM-DD");
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return new Intl.DateTimeFormat(locale, {
    timeZone: "UTC",
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(date);
}

export type LocalDateTimeProblem = "ambiguous" | "nonexistent" | "invalid";

interface LocalDateTimeParts {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
  millisecond: number;
}

function localDateTimeParts(value: string): LocalDateTimeParts | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?$/.exec(value);
  if (!match) return undefined;
  const parts = {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4]),
    minute: Number(match[5]),
    second: Number(match[6] ?? 0),
    millisecond: Number((match[7] ?? "").padEnd(3, "0") || 0),
  };
  const date = new Date(0);
  date.setUTCFullYear(parts.year, parts.month - 1, parts.day);
  date.setUTCHours(parts.hour, parts.minute, parts.second, parts.millisecond);
  if (
    date.getUTCFullYear() !== parts.year ||
    date.getUTCMonth() !== parts.month - 1 ||
    date.getUTCDate() !== parts.day ||
    parts.hour > 23 || parts.minute > 59 || parts.second > 59
  ) return undefined;
  return parts;
}

function wallClockEpoch(parts: LocalDateTimeParts): number {
  const date = new Date(0);
  date.setUTCFullYear(parts.year, parts.month - 1, parts.day);
  date.setUTCHours(parts.hour, parts.minute, parts.second, parts.millisecond);
  return date.getTime();
}

function zonedParts(date: Date, formatter: Intl.DateTimeFormat): LocalDateTimeParts {
  const fields = Object.fromEntries(
    formatter.formatToParts(date).map(({ type, value }) => [type, value]),
  );
  return {
    year: Number(fields.year),
    month: Number(fields.month),
    day: Number(fields.day),
    hour: Number(fields.hour),
    minute: Number(fields.minute),
    second: Number(fields.second),
    millisecond: date.getUTCMilliseconds(),
  };
}

function resolveLocalDateTime(
  localDateTime: string,
  timezone: string,
): { problem: LocalDateTimeProblem } | { instant: Date } {
  const target = localDateTimeParts(localDateTime);
  if (!target) return { problem: "invalid" };

  try {
    const formatter = new Intl.DateTimeFormat("en-GB", {
      timeZone: timezone,
      calendar: "iso8601",
      numberingSystem: "latn",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    });
    const wallTime = wallClockEpoch(target);
    const offsets = new Set<number>();
    for (const hours of [-36, -24, -12, 0, 12, 24, 36]) {
      const sample = new Date(wallTime + hours * 60 * 60 * 1000);
      offsets.add(wallClockEpoch(zonedParts(sample, formatter)) - sample.getTime());
    }

    const candidates = new Map<number, Date>();
    for (const offset of offsets) {
      const instant = new Date(wallTime - offset);
      const local = zonedParts(instant, formatter);
      if (
        local.year === target.year && local.month === target.month && local.day === target.day &&
        local.hour === target.hour && local.minute === target.minute && local.second === target.second &&
        local.millisecond === target.millisecond
      ) candidates.set(instant.getTime(), instant);
    }
    if (candidates.size === 0) return { problem: "nonexistent" };
    if (candidates.size > 1) return { problem: "ambiguous" };
    return { instant: [...candidates.values()][0] };
  } catch {
    return { problem: "invalid" };
  }
}

export function getLocalDateTimeProblem(
  localDateTime: string,
  timezone: string,
): LocalDateTimeProblem | undefined {
  const result = resolveLocalDateTime(localDateTime, timezone);
  return "problem" in result ? result.problem : undefined;
}

export function localDateTimeProblemMessage(
  problem: LocalDateTimeProblem,
  timezone: string,
): string {
  if (problem === "ambiguous") {
    return `这个时间在 ${timezone} 会出现两次，无法确定具体时刻。请选择另一个时间。`;
  }
  if (problem === "nonexistent") {
    return `这个时间在 ${timezone} 不存在（时钟会跳过这段时间）。请选择另一个时间。`;
  }
  return `请输入有效的日期和时间，并检查账户时区（${timezone}）。`;
}

export function toUtcISOString(localDateTime: string, timezone: string): string {
  const result = resolveLocalDateTime(localDateTime, timezone);
  if ("problem" in result) {
    throw new RangeError(localDateTimeProblemMessage(result.problem, timezone));
  }
  return result.instant.toISOString();
}

export function toDateTimeLocalValue(value: string | Date, timezone: string): string {
  const date = typeof value === "string" ? parseApiDateTime(value) : value;
  return formatInTimeZone(date, timezone, "yyyy-MM-dd'T'HH:mm");
}

export function getLocalDateKey(value: string | Date, timezone: string): string {
  const date = typeof value === "string" ? parseApiDateTime(value) : value;
  return formatInTimeZone(date, timezone, "yyyy-MM-dd");
}

export function getTimezoneLabel(timezone: string, now = new Date()): string {
  const offset = formatInTimeZone(now, timezone, "XXX");
  return `${timezone} (UTC${offset === "Z" ? "+00:00" : offset})`;
}
