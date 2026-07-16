import { formatInTimeZone, fromZonedTime } from "date-fns-tz";

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

export function toUtcISOString(localDateTime: string, timezone: string): string {
  return fromZonedTime(localDateTime, timezone).toISOString();
}

export function getTimezoneLabel(timezone: string, now = new Date()): string {
  const offset = formatInTimeZone(now, timezone, "XXX");
  return `${timezone} (UTC${offset === "Z" ? "+00:00" : offset})`;
}

