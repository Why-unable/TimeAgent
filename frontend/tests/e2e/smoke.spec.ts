import { expect, test } from "@playwright/test";

test("renders the system status shell", async ({ page }) => {
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({
      status: 403,
      json: { detail: "Authentication credentials were not provided." },
    });
  });
  await page.route("**/health/ready", async (route) => {
    await route.fulfill({
      json: { status: "ready", checks: { database: "ok", redis: "ok" } },
    });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "系统状态" })).toBeVisible();
});

test("reads and updates time preferences", async ({ page }) => {
  let timezone = "Asia/Shanghai";
  await page.route("**/api/v1/preferences/me/", async (route) => {
    if (route.request().method() === "PATCH") {
      const changes = route.request().postDataJSON() as { timezone: string };
      timezone = changes.timezone;
    }
    await route.fulfill({
      json: {
        timezone,
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
      },
    });
  });

  await page.goto("/settings/time");
  await expect(page.getByRole("heading", { name: "时间偏好" })).toBeVisible();
  await page.getByLabel("IANA 时区").fill("Europe/London");
  await page.getByRole("button", { name: "保存偏好" }).click();
  await expect(page.getByRole("status")).toHaveText("时间偏好已保存。");
  expect(timezone).toBe("Europe/London");
});

test("renders the Today workspace from the summary API", async ({ page }) => {
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({ status: 403, json: { detail: "Not authenticated." } });
  });
  await page.route("**/api/v1/today/", async (route) => {
    await route.fulfill({
      json: {
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
      },
    });
  });

  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "今天" })).toBeVisible();
  await expect(page.getByText("今天没有后续日程")).toBeVisible();
  await expect(page.getByText("今日安排没有检测到冲突。")).toBeVisible();
});
