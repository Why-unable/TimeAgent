import { expect, test } from "@playwright/test";

test.use({ timezoneId: "Europe/London" });

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
  await page.addInitScript(() => {
    window.localStorage.setItem("time-agent:onboarding:1:v1", "completed");
  });
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
  await page.route("**/api/v1/insights/", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/integrations/calendar/connections/", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/app-updates/android/latest/", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        release: {
          version_code: 12,
          version_name: "1.1.8",
          download_url: "https://steward.example.test/releases/timeagent-1.1.8.apk",
          sha256: "a".repeat(64),
          size_bytes: 4_194_304,
          release_notes: "测试版本",
          published_at: "2026-08-27T00:00:00Z",
          minimum_supported_version_code: 1,
        },
      },
    }),
  );
  await page.route("**/api/v1/chat/conversations/**", (route) => {
    if (route.request().url().endsWith("/conversations/")) {
      return route.fulfill({ json: [] });
    }
    return route.fulfill({ json: { runs: [] } });
  });
  await page.route("**/api/v1/action-proposals/**", (route) => route.fulfill({ json: [] }));
});

test.describe("desktop workspace", () => {
  test("opens Planning with a natural-language goal instead of planner configuration", async ({ page }) => {
    await page.route("**/api/v1/planning/automation-policies/", (route) => route.fulfill({ json: [] }));
    await page.route("**/api/v1/time-memory/me/capacity-forecast/**", (route) => route.fulfill({ json: {
      total_schedulable_capacity_minutes: 480, remaining_free_minutes: 480, committed_minutes: 0, unplanned_minutes: 0, risk: "within_capacity", reason_codes: [],
    } }));
    await page.goto("/planning");
    const goal = page.getByRole("textbox", { name: "安排目标" });
    await expect(goal).toHaveValue("帮我安排明天的任务");
    await goal.fill("明天帮我安排任务，上午留给论文");
    await page.getByRole("button", { name: "让助理安排" }).click();
    await expect(page).toHaveURL(/\/chat\?prompt=/);
    await expect(page.getByRole("textbox", { name: "消息" })).toHaveValue("明天帮我安排任务，上午留给论文");
    await expect(page.getByRole("button", { name: "高级规划设置" })).toHaveCount(0);
  });

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

  test("shows a scannable Android download dialog without overflowing", async ({ page }, testInfo) => {
    await page.goto("/today");
    await page.getByRole("button", { name: "下载手机 App" }).click();

    const dialog = page.getByRole("dialog", { name: "下载 Time Agent" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("手机扫码下载")).toBeVisible();
    await expect(dialog.getByRole("link", { name: "直接下载 APK" })).toHaveAttribute(
      "href",
      "https://steward.example.test/releases/timeagent-1.1.8.apk",
    );
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
      true,
    );

    const screenshotPath = "test-results/desktop-android-download.png";
    await page.screenshot({ path: screenshotPath, fullPage: true });
    await testInfo
      .attach("desktop-android-download", { path: screenshotPath, contentType: "image/png" })
      .catch(() => undefined);
  });

  test("keeps all sidebar settings reachable in a short desktop viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 620 });
    await page.goto("/today");

    const navigation = page.getByTestId("desktop-sidebar-navigation");
    const appSettings = navigation.getByRole("link", { name: /应用设置/ });
    const scrollState = await navigation.evaluate((element) => ({
      clientHeight: element.clientHeight,
      overflowY: getComputedStyle(element).overflowY,
      scrollHeight: element.scrollHeight,
    }));

    expect(scrollState.overflowY).toBe("auto");
    expect(scrollState.scrollHeight).toBeGreaterThan(scrollState.clientHeight);
    await expect(appSettings).not.toBeInViewport();

    await navigation.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
    });

    await expect(appSettings).toBeInViewport();
  });

  test("plans and applies a day plan in two decisions without showing planner internals", async ({ page }) => {
    const task = {
      id: "21111111-1111-4111-8111-111111111111",
      project: "",
      parent_task: null,
      title: "准备周会材料",
      description: "",
      status: "pending",
      priority: "high",
      due_at: null,
      estimated_minutes: 60,
      planned_start_at: null,
      planned_end_at: null,
      actual_started_at: null,
      completed_at: null,
      source: "local",
      tags: [],
      version: 1,
      created_at: "2026-07-30T01:00:00Z",
      updated_at: "2026-07-30T01:00:00Z",
    };
    let applied = false;
    let generatedRangeStart = "";
    await page.route("**/api/v1/tasks/", (route) => route.fulfill({ json: [task] }));
    await page.route("**/api/v1/planning/automation-policies/", (route) => route.fulfill({ json: [] }));
    await page.route("**/api/v1/time-memory/me/capacity-forecast/**", (route) => route.fulfill({
      json: { total_schedulable_capacity_minutes: 480, remaining_free_minutes: 420, committed_minutes: 60, unplanned_minutes: 60, risk: "within_capacity", reason_codes: [] },
    }));
    await page.route("**/api/v1/planning/plans/", async (route) => {
      if (route.request().method() === "POST") {
        generatedRangeStart = String(route.request().postDataJSON().range_start);
        return route.fulfill({ status: 201, json: {
          id: "41111111-1111-4111-8111-111111111111",
          strategy: "plan_tasks_only",
          status: "draft",
          version: 1,
          created_at: "2026-07-30T01:00:00Z",
          updated_at: "2026-07-30T01:00:00Z",
          expires_at: "2026-07-30T02:00:00Z",
          applied_at: null,
          items: [{ task_id: task.id, state: "placed", start_at: "2026-07-31T01:00:00Z", end_at: "2026-07-31T02:00:00Z", locked: false, reason_codes: [] }],
        } });
      }
      return route.continue();
    });
    await page.route("**/api/v1/planning/plans/*/apply/", (route) => {
      applied = true;
      return route.fulfill({ status: 200, json: { id: "41111111-1111-4111-8111-111111111111", strategy: "plan_tasks_only", status: "applied", version: 2, created_at: "2026-07-30T01:00:00Z", applied_at: "2026-07-30T01:01:00Z", items: [] } });
    });

    await page.goto("/planning");
    await page.getByRole("button", { name: "高级规划设置" }).click();
    await expect(page.getByRole("checkbox", { name: /准备周会材料/ })).toBeChecked();
    await page.getByRole("button", { name: "Plan My Day" }).click();
    const userDate = (await page.getByRole("textbox", { name: "开始" }).inputValue()).slice(0, 10);
    await page.getByRole("button", { name: "生成草案" }).click();
    expect(generatedRangeStart).toBe(new Date(`${userDate}T00:00:00+08:00`).toISOString());
    await expect(page.getByText("草案", { exact: true })).toBeVisible();
    await expect(page.getByText("有效至", { exact: false })).toHaveCount(0);
    await expect(page.getByText(/v\d|strategy|reason_codes|plan_tasks_only/)).toHaveCount(0);
    for (const width of [320, 375, 430, 1280]) {
      await page.setViewportSize({ width, height: 800 });
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expect(page.getByText("准备周会材料").first()).toBeVisible();
    }
    await page.getByRole("button", { name: "应用计划" }).click();
    await expect(page.getByText("计划已应用。", { exact: true })).toBeVisible();
    expect(applied).toBe(true);
  });
});
