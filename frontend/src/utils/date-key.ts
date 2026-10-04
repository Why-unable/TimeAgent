function dateFromKey(dateKey: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateKey);
  if (!match) throw new RangeError("Date key must use YYYY-MM-DD");
  const date = new Date(0);
  date.setUTCFullYear(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  date.setUTCHours(0, 0, 0, 0);
  if (date.toISOString().slice(0, 10) !== dateKey) {
    throw new RangeError("Date key must be a valid calendar date");
  }
  return date;
}

export function addDaysToDateKey(dateKey: string, days: number): string {
  if (!Number.isInteger(days)) throw new RangeError("Day offset must be an integer");
  const date = dateFromKey(dateKey);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function mondayOfDateKey(dateKey: string): string {
  const date = dateFromKey(dateKey);
  const mondayOffset = (date.getUTCDay() + 6) % 7;
  return addDaysToDateKey(dateKey, -mondayOffset);
}

/** Build an absolute API window that covers every local instant in the date range
 * for all IANA UTC offsets. Callers filter returned objects by their user-zone date. */
export function expandedUtcDateRange(
  startDateKey: string,
  endDateKeyExclusive: string,
  paddingHours = 36,
) {
  if (!Number.isFinite(paddingHours) || paddingHours < 0) {
    throw new RangeError("Padding must be a non-negative number of hours");
  }
  const start = dateFromKey(startDateKey).getTime() - paddingHours * 60 * 60 * 1000;
  const end = dateFromKey(endDateKeyExclusive).getTime() + paddingHours * 60 * 60 * 1000;
  if (end <= start) throw new RangeError("End date must follow start date");
  return {
    endsAfter: new Date(start).toISOString(),
    startsBefore: new Date(end).toISOString(),
  };
}

export function dateKeyAsUtcDate(dateKey: string): Date {
  return dateFromKey(dateKey);
}
