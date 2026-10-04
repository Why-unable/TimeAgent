import { describe, expect, it } from "vitest";

import {
  addDaysToDateKey,
  dateKeyAsUtcDate,
  expandedUtcDateRange,
  mondayOfDateKey,
} from "../src/utils/date-key";

describe("date-key helpers", () => {
  it("adds calendar days across month and leap-year boundaries", () => {
    expect(addDaysToDateKey("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDaysToDateKey("2028-02-28", 1)).toBe("2028-02-29");
    expect(addDaysToDateKey("2028-03-01", -1)).toBe("2028-02-29");
  });

  it("starts weeks on Monday and treats date keys as UTC calendar dates", () => {
    expect(mondayOfDateKey("2026-10-04")).toBe("2026-09-28");
    expect(mondayOfDateKey("2026-10-05")).toBe("2026-10-05");
    expect(dateKeyAsUtcDate("2026-10-05").toISOString()).toBe("2026-10-05T00:00:00.000Z");
  });

  it("expands a date range in absolute time to cover user-zone offsets", () => {
    expect(expandedUtcDateRange("2026-10-05", "2026-10-12")).toEqual({
      endsAfter: "2026-10-03T12:00:00.000Z",
      startsBefore: "2026-10-13T12:00:00.000Z",
    });
  });

  it("rejects invalid date keys and non-integer offsets", () => {
    expect(() => addDaysToDateKey("2026-02-30", 1)).toThrow(RangeError);
    expect(() => addDaysToDateKey("2026-10-05", 0.5)).toThrow(RangeError);
    expect(() => expandedUtcDateRange("2026-10-05", "2026-10-12", -1)).toThrow(RangeError);
  });
});
