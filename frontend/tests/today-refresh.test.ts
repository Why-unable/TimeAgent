import { describe, expect, it } from "vitest";

import type { TodaySummary } from "../src/api/today";
import { nextTodayRefreshDelay } from "../src/features/today/hooks";

const summary = {
  day_end_at: "2026-10-04T16:00:00Z",
  execution_now: [],
  execution_next: [{
    kind: "task",
    id: "task-1",
    title: "准备评审",
    start_at: "2026-10-03T10:00:00Z",
    end_at: "2026-10-03T10:30:00Z",
    status: "pending",
    due_at: null,
  }],
  execution_later: [],
} as unknown as TodaySummary;

describe("Today summary refresh scheduling", () => {
  it("refreshes shortly after the next server bucket boundary", () => {
    expect(nextTodayRefreshDelay(summary, Date.parse("2026-10-03T09:59:00Z"))).toBe(61_000);
  });

  it("caps background freshness polling and skips past boundaries", () => {
    expect(nextTodayRefreshDelay(summary, Date.parse("2026-10-03T11:00:00Z"))).toBe(5 * 60_000);
  });
});
