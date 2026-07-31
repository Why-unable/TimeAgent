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
  updated_at: "2026-07-31T00:00:00Z",
};

const todaySummary = {
  date: "2026-07-31",
  timezone: "Asia/Shanghai",
  generated_at: "2026-07-31T01:00:00Z",
  day_start_at: "2026-07-30T16:00:00Z",
  day_end_at: "2026-07-31T16:00:00Z",
  events: [
    {
      id: "event-1",
      title: "产品复盘",
      start_at: "2026-07-31T02:00:00Z",
      end_at: "2026-07-31T03:00:00Z",
      timezone: "Asia/Shanghai",
      source: "local",
      status: "confirmed",
      version: 1,
    },
  ],
  planned_tasks: [],
  due_tasks: [],
  overdue_tasks: [],
  pending_reminders: [],
  conflicts: [],
  next_event: null,
  minutes_until_next_event: null,
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me/", (route) =>
    route.fulfill({
      json: {
        id: 1,
        email: "desktop@example.test",
        display_name: "桌面用户",
        is_staff: false,
      },
    }),
  );
  await page.route("**/api/v1/preferences/me/", (route) => route.fulfill({ json: preference }));
  await page.route("**/api/v1/today/", (route) => route.fulfill({ json: todaySummary }));
  await page.route("**/api/v1/tasks/**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/events/**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/reminders/**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/chat/conversations/**", (route) => {
    if (route.request().url().endsWith("/conversations/")) {
      return route.fulfill({ json: [] });
    }
    return route.fulfill({ json: { runs: [] } });
  });
  await page.route("**/api/v1/action-proposals/**", (route) => route.fulfill({ json: [] }));
});

test.describe("desktop workspace", () => {
  test("aggregates schedule navigation and keeps the bright wide-screen shell", async ({ page }) => {
    await page.goto("/tasks");

    const sidebar = page.getByTestId("desktop-sidebar");
    await expect(sidebar).toBeVisible();
    await expect(page.getByRole("navigation", { name: "移动端主导航" })).toBeHidden();
    await expect(sidebar.getByRole("link", { name: /日程/ })).toHaveCount(1);
    await expect(sidebar.getByRole("link", { name: /日程/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(page.getByRole("navigation", { name: "时间管理工作区" })).toBeVisible();

    const colors = await page.evaluate(() => ({
      body: getComputedStyle(document.body).backgroundColor,
      sidebar: getComputedStyle(document.querySelector("[data-testid='desktop-sidebar']")!).backgroundColor,
    }));
    expect(colors.body).not.toBe("rgb(2, 6, 23)");
    expect(colors.sidebar).not.toBe("rgb(15, 23, 42)");
  });

  test("captures desktop pages for visual review", async ({ page }, testInfo) => {
    for (const [name, path] of [
      ["today", "/today"],
      ["chat", "/chat"],
      ["calendar", "/calendar"],
      ["tasks", "/tasks"],
    ] as const) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const screenshotPath = `test-results/desktop-${name}.png`;
      await page.screenshot({ path: screenshotPath, fullPage: true });
      await testInfo
        .attach(`desktop-${name}`, { path: screenshotPath, contentType: "image/png" })
        .catch(() => undefined);
    }
  });
});
