import { expect, test } from "@playwright/test";

const preference = {
  timezone: "Asia/Shanghai",
  locale: "zh-CN",
  workday_start: "09:00:00",
  workday_end: "18:00:00",
  sleep_start: "23:00:00",
  sleep_end: "07:00:00",
  default_event_duration_minutes: 60,
  preferred_focus_periods: [],
  default_reminder_offsets: [],
  weather_location: "",
  news_topics: [],
  briefing_time: "08:00:00",
  planning_rules: {},
  updated_at: "2026-07-17T00:00:00Z",
};

const emptyTodaySummary = {
  date: "2026-07-20",
  timezone: "Asia/Shanghai",
  generated_at: "2026-07-20T04:00:00Z",
  day_start_at: "2026-07-19T16:00:00Z",
  day_end_at: "2026-07-20T16:00:00Z",
  events: [],
  planned_tasks: [],
  due_tasks: [],
  overdue_tasks: [],
  pending_reminders: [],
  conflicts: [],
  next_event: null,
  minutes_until_next_event: null,
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("time-agent:onboarding:1:v1", "completed");
  });
  await page.route("**/api/v1/auth/me/", (route) =>
    route.fulfill({
      json: { id: 1, email: "e2e@example.test", display_name: "E2E User", is_staff: false },
    }),
  );
  await page.route("**/api/v1/auth/csrf/", (route) =>
    route.fulfill({ json: { csrfToken: "e2e-csrf" } }),
  );
  await page.route("**/api/v1/preferences/me/", (route) => route.fulfill({ json: preference }));
  await page.route("**/api/v1/today/", (route) => route.fulfill({ json: emptyTodaySummary }));
  await page.route("**/api/v1/tasks/**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/events/**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/reminders/**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/insights/", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/integrations/calendar/connections/", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/planning/automation-policies/", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/time-memory/me/capacity-forecast/**", (route) =>
    route.fulfill({
      json: {
        range_start: "2026-07-20T01:00:00Z",
        range_end: "2026-07-27T01:00:00Z",
        available_minutes: 480,
        committed_minutes: 120,
        unplanned_minutes: 60,
        risk: "within_capacity",
        reason_codes: [],
      },
    }),
  );
  await page.route("**/api/v1/chat/conversations/**", (route) => {
    if (route.request().url().endsWith("/conversations/")) {
      route.fulfill({ json: [] });
      return;
    }
    route.fulfill({ json: { runs: [] } });
  });
  await page.route("**/api/v1/action-proposals/**", (route) => route.fulfill({ json: [] }));
});

async function assertNoHorizontalScroll(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
}

test.describe("mobile shell", () => {
  test("bottom nav shows exactly four items and no independent 日历 entry", async ({ page }) => {
    await page.goto("/today");
    const nav = page.getByRole("navigation", { name: "移动端主导航" });
    await expect(nav).toBeVisible();
    // 3 primary links + 更多 button
    await expect(nav.locator("a")).toHaveCount(3);
    await expect(nav.getByText("今天")).toBeVisible();
    await expect(nav.getByText("聊天")).toBeVisible();
    await expect(nav.getByText("日程")).toBeVisible();
    await expect(page.getByRole("button", { name: "更多" })).toBeVisible();
    await expect(nav.getByText("日历", { exact: true })).toHaveCount(0);
  });

  for (const path of ["/calendar", "/tasks", "/planning", "/reminders"]) {
    test(`highlights 日程 tab on ${path}`, async ({ page }) => {
      await page.goto(path);
      const nav = page.getByRole("navigation", { name: "移动端主导航" });
      const scheduleLink = nav.getByRole("link", { name: /日程/ });
      await expect(scheduleLink).toHaveAttribute("aria-current", "page");
    });
  }

  test("exposes briefings from the more drawer", async ({ page }) => {
    await page.goto("/today");
    await page.getByRole("button", { name: "更多" }).click();
    await expect(page.getByRole("link", { name: /简报/ })).toHaveAttribute("href", "/briefings");
  });

  test("no horizontal scroll on primary workspaces", async ({ page }) => {
    for (const path of ["/today", "/chat", "/calendar", "/tasks", "/planning"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await assertNoHorizontalScroll(page);
    }
  });

  test("chat composer stays above the bottom nav", async ({ page }) => {
    await page.goto("/chat");
    const composer = page.getByRole("textbox", { name: "消息" });
    await expect(composer).toBeVisible();
    const composerBox = await composer.boundingBox();
    const navBox = await page.getByRole("navigation", { name: "移动端主导航" }).boundingBox();
    expect(composerBox).not.toBeNull();
    expect(navBox).not.toBeNull();
    if (composerBox && navBox) {
      expect(composerBox.y + composerBox.height).toBeLessThanOrEqual(navBox.y + 1);
    }
  });

  test("month view renders all six weeks", async ({ page }) => {
    await page.goto("/calendar");
    // Wait for FullCalendar to mount and switch to month view
    await page.getByRole("tab", { name: "月" }).click();
    // FullCalendar's day cells expose role="button" with an aria-label of the date.
    // Wait for at least one cell to appear, then count.
    const dayCellSelector = ".fc-day, [data-date], .fc-daygrid-day";
    await page
      .locator(dayCellSelector)
      .first()
      .waitFor({ timeout: 10_000 });
    const dayCount = await page.locator(dayCellSelector).count();
    // 6 rows x 7 days = 42 cells (FullCalendar renders 42 for fixedWeekCount)
    expect(dayCount).toBeGreaterThanOrEqual(42);
  });

  test("segmented control switches between 月/周/日 views", async ({ page }) => {
    await page.goto("/calendar");
    for (const label of ["月", "周", "日"]) {
      await page.getByRole("tab", { name: label }).click();
      await expect(page.getByRole("tab", { name: label })).toHaveAttribute("aria-selected", "true");
    }
  });

  test("captures mobile page screenshots", async ({ page }, testInfo) => {
    for (const [name, path] of [
      ["today", "/today"],
      ["chat", "/chat"],
      ["calendar", "/calendar"],
      ["tasks", "/tasks"],
    ] as const) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await page.screenshot({ path: `test-results/mobile-${name}.png`, fullPage: true });
      testInfo.attach(`mobile-${name}`, {
        path: `test-results/mobile-${name}.png`,
        contentType: "image/png",
      }).catch(() => undefined);
    }
  });
});
