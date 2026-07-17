import { describe, expect, it } from "vitest";

import {
  formatDateKey,
  formatInUserTimezone,
  formatTimeInUserTimezone,
  getTimezoneLabel,
  parseApiDateTime,
  toUtcISOString,
} from "../src/utils/datetime";

describe("datetime utilities", () => {
  it("requires an explicit API timezone offset", () => {
    expect(() => parseApiDateTime("2026-07-17T10:00:00")).toThrow(
      "explicit UTC offset",
    );
    expect(parseApiDateTime("2026-07-17T10:00:00Z").toISOString()).toBe(
      "2026-07-17T10:00:00.000Z",
    );
  });

  it("formats API time in the configured user timezone", () => {
    expect(
      formatInUserTimezone(
        "2026-07-17T07:00:00Z",
        "Asia/Shanghai",
        "zh-CN",
      ),
    ).toContain("15:00");
    expect(
      formatTimeInUserTimezone("2026-07-17T07:00:00Z", "Asia/Shanghai"),
    ).toBe("15:00");
    expect(formatDateKey("2026-07-20")).toContain("2026年7月20日");
  });

  it("converts a local time and IANA timezone to UTC", () => {
    expect(toUtcISOString("2026-07-17T15:00:00", "Asia/Shanghai")).toBe(
      "2026-07-17T07:00:00.000Z",
    );
  });

  it("returns a timezone label with its current offset", () => {
    expect(
      getTimezoneLabel("Asia/Shanghai", new Date("2026-07-17T00:00:00Z")),
    ).toBe("Asia/Shanghai (UTC+08:00)");
  });
});
