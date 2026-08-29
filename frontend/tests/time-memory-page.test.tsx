import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TimeMemoryPage } from "../src/pages/time-memory-page";

const preference = {
  timezone: "Asia/Shanghai",
  locale: "zh-CN",
  time_memory_enabled: true,
  time_memory_allow_generation: true,
  time_memory_allow_context_injection: true,
};

const profile = {
  schema_version: 2,
  user_id: "1",
  generated_at: "2026-08-06T00:00:00Z",
  data_until: "2026-08-06T00:00:00Z",
  timezone: "Asia/Shanghai",
  common_places: [
    {
      place_id: "office",
      name: "办公室",
      normalized_name: "办公室",
      event_count: 8,
      total_scheduled_hours: 24,
      typical_weekdays: [1, 2, 3],
      typical_time_ranges: ["09:00-10:00"],
      first_seen_at: "2026-01-01T01:00:00Z",
      last_seen_at: "2026-08-05T10:00:00Z",
      confidence: 0.8,
      score: 0.8,
    },
  ],
  behavior_windows: {
    "7d": {
      window: "7d",
      start_date: "2026-07-31",
      end_date: "2026-08-06",
      sample_days: 7,
      event_count: 4,
      task_count: 2,
      reminder_count: 1,
      completed_task_count: 1,
      cancelled_task_count: 0,
      source_distribution: { web: 2 },
      schedule_pattern: {
        total_scheduled_hours: 8,
        average_daily_scheduled_hours: 1.1,
        median_daily_scheduled_hours: 1,
        scheduled_day_count: 4,
        busy_day_count: 0,
        light_day_count: 2,
        rest_day_count: 3,
        consecutive_busy_days_max: 0,
        weekday_average_hours: 1.2,
        weekend_average_hours: 0,
        peak_time_ranges: ["09:00-10:00"],
        work_rest_balance: "balanced",
        summary: "最近安排较均衡。",
      },
      planning_pattern: {
        created_event_count: 4,
        creation_session_count: 2,
        batch_creation_session_count: 0,
        batch_creation_ratio: 0,
        incremental_creation_ratio: 1,
        average_lead_time_hours: 24,
        median_lead_time_hours: 24,
        last_minute_creation_ratio: 0.5,
        long_horizon_creation_ratio: 0,
        typical_creation_time_ranges: ["08:00-09:00"],
        planning_style: "incremental",
        summary: "近期更倾向于逐步添加安排。",
      },
      change_pattern: {
        modified_event_count: 1,
        rescheduled_event_count: 1,
        postponed_event_count: 1,
        advanced_event_count: 0,
        cancelled_event_count: 0,
        completed_event_count: 0,
        reschedule_ratio: 0.25,
        postpone_ratio: 1,
        cancellation_ratio: 0,
        completion_ratio: null,
        average_reschedule_delta_hours: 2,
        dominant_change_behavior: "postpone",
        summary: "近期有少量日程调整。",
      },
      summary: "最近安排较均衡。",
      confidence: 0.8,
    },
  },
  stable_patterns: [],
  profile_summary: "近期安排较均衡。",
  version: 3,
};

const profileWithAdaptivePlanning = {
  ...profile,
  behavior_windows: {
    "7d": {
      ...profile.behavior_windows["7d"],
      adaptive_planning_pattern: {
        automated_move_count: 3,
        reverted_move_count: 1,
        user_modified_after_move_count: 1,
        accepted_move_count: 1,
        median_move_minutes: 30,
        revert_or_modify_ratio: 2 / 3,
        confidence: 0.6,
        summary: "自动调整 3 次，其中 1 次保留。",
      },
    },
  },
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <TimeMemoryPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TimeMemoryPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the profile and supports disabling memory and forgetting a place", async () => {
    const requests: Array<{ url: string; method: string; body?: string }> = [];
    vi.stubGlobal("confirm", vi.fn(() => true));
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      requests.push({ url, method, body: typeof init?.body === "string" ? init.body : undefined });
      if (url.endsWith("/api/v1/preferences/me/") && method === "GET") return new Response(JSON.stringify(preference));
      if (url.endsWith("/api/v1/time-memory/me/") && method === "GET") return new Response(JSON.stringify({ profile, refresh_status: "clean", dirty_at: null, last_completed_at: "2026-08-06T00:00:00Z", last_error: "" }));
      if (url.endsWith("/api/v1/preferences/me/") && method === "PATCH") return new Response(JSON.stringify({ ...preference, ...JSON.parse(String(init?.body)) }));
      if (url.includes("/api/v1/time-memory/me/places/office/") && method === "DELETE") return new Response(null, { status: 204 });
      throw new Error(`Unexpected request: ${method} ${url}`);
    }));

    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText("办公室")).toBeInTheDocument();
    expect(screen.getByText("近期安排较均衡。")).toBeInTheDocument();

    await user.click(screen.getByLabelText("启用长期时间记忆"));
    await user.click(screen.getByRole("button", { name: "删除常用地点 办公室" }));

    await waitFor(() => {
      expect(requests.some((request) => request.method === "DELETE" && request.url.includes("places/office"))).toBe(true);
      expect(requests.some((request) => request.method === "PATCH" && request.body?.includes("time_memory_enabled"))).toBe(true);
    });
  });

  it("shows adaptive planning evidence when a rebuilt profile contains it", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/v1/preferences/me/") && method === "GET") return new Response(JSON.stringify(preference));
      if (url.endsWith("/api/v1/time-memory/me/") && method === "GET") return new Response(JSON.stringify({ profile: profileWithAdaptivePlanning, refresh_status: "clean", dirty_at: null, last_completed_at: "2026-08-06T00:00:00Z", last_error: "" }));
      throw new Error(`Unexpected request: ${method} ${url}`);
    }));

    renderPage();
    expect(await screen.findByText("自动调整 3 次，其中 1 次保留。")).toBeInTheDocument();
  });
});
