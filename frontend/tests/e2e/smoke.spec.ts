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
