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
  unfinished_tasks: [],
  completed_tasks: [],
  pending_reminders: [],
  conflicts: [],
  next_event: null,
  minutes_until_next_event: null,
  execution_now: [],
  execution_next: [],
  execution_later: [],
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
  await page.route("**/api/v1/briefings/runs/", (route) => route.fulfill({ json: [] }));
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
  await page.route("**/api/v1/interactions/**", (route) => route.fulfill({ json: [] }));
});

async function assertNoHorizontalScroll(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(() => {
    const clientWidth = document.documentElement.clientWidth;
    const initialY = window.scrollY;
    window.scrollTo(10000, initialY);
    const documentScrollX = window.scrollX;
    window.scrollTo(0, initialY);
    return {
      innerWidth: window.innerWidth,
      documentScrollX,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth,
      mainWidth: document.querySelector("main")?.getBoundingClientRect().width,
      dateRail: (() => {
        const rail = document.querySelector<HTMLElement>('[aria-label="本周日期"]');
        return rail ? {
          left: rail.getBoundingClientRect().left,
          right: rail.getBoundingClientRect().right,
          width: rail.getBoundingClientRect().width,
          clientWidth: rail.clientWidth,
          scrollWidth: rail.scrollWidth,
          overflowX: getComputedStyle(rail).overflowX,
        } : null;
      })(),
      offenders: Array.from(document.querySelectorAll<HTMLElement>("body *"))
        .map((element) => ({
          tag: element.tagName,
          className: typeof element.className === "string" ? element.className : "",
          left: Math.round(element.getBoundingClientRect().left),
          right: Math.round(element.getBoundingClientRect().right),
          width: Math.round(element.getBoundingClientRect().width),
        }))
        .filter((element) => element.width > 0 && (element.left < -1 || element.right > clientWidth + 1))
        .slice(0, 8),
    };
  });
  expect(overflow.documentScrollX, JSON.stringify(overflow)).toBe(0);
}

function contrastRatio(foreground: string, background: string) {
  const luminance = (color: string) => {
    const channels = color.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [];
    const linear = channels.map((channel) => {
      const normalized = channel / 255;
      return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
  };
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

test.describe("mobile shell", () => {
  test("bottom nav shows Today, Assistant, Plan, and Me", async ({ page }) => {
    await page.goto("/today");
    const nav = page.getByRole("navigation", { name: "移动端主导航" });
    await expect(nav).toBeVisible();
    // 3 primary links + Me button
    await expect(nav.locator("a")).toHaveCount(3);
    await expect(nav.getByText("今天")).toBeVisible();
    await expect(nav.getByText("助理")).toBeVisible();
    await expect(nav.getByText("计划")).toBeVisible();
    await expect(page.getByRole("button", { name: "我的" })).toBeVisible();
    await expect(nav.getByText("日历", { exact: true })).toHaveCount(0);
  });

  for (const path of ["/schedule", "/calendar", "/tasks", "/planning"]) {
    test(`highlights 计划 tab on ${path}`, async ({ page }) => {
      await page.goto(path);
      const nav = page.getByRole("navigation", { name: "移动端主导航" });
      await expect(nav.getByRole("link", { name: /计划/ })).toHaveAttribute("aria-current", "page");
    });
  }

  test("marks Me as current for reminders and exposes low-frequency destinations", async ({ page }) => {
    await page.goto("/reminders");
    const meButton = page.getByRole("button", { name: "我的" });
    await expect(meButton).toHaveAttribute("aria-current", "page");
    await meButton.click();
    await expect(page.getByRole("dialog", { name: "我的" })).toBeVisible();
    await expect(page.getByRole("link", { name: /简报/ })).toHaveAttribute("href", "/briefings");
    await expect(page.getByRole("link", { name: /应用设置/ })).toHaveAttribute("href", "/settings/app");
  });

  test("Me drawer closes with Escape", async ({ page }) => {
    await page.goto("/today");
    await page.getByRole("button", { name: "我的" }).click();
    await expect(page.getByRole("dialog", { name: "我的" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "我的" })).toHaveCount(0);
  });

  test("no horizontal scroll on primary workspaces", async ({ page }) => {
    for (const path of ["/today", "/chat", "/schedule", "/calendar", "/tasks", "/planning"]) {
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

  test("chat quick actions wrap into visible rows on phone widths", async ({ page }) => {
    for (const width of [320, 360, 393, 430]) {
      await page.setViewportSize({ width, height: 844 });
      await page.goto("/chat");
      const group = page.getByRole("group", { name: "常用快捷操作" });
      await expect(group.getByRole("button")).toHaveCount(4);
      const viewportWidth = await page.evaluate(() => document.documentElement.clientWidth);
      const buttonBoxes = await group.getByRole("button").evaluateAll((buttons) =>
        buttons.map((button) => {
          const rect = button.getBoundingClientRect();
          return { left: rect.left, right: rect.right, top: rect.top };
        }),
      );
      expect(buttonBoxes.every((box) => box.left >= 0 && box.right <= viewportWidth)).toBe(true);
      expect(new Set(buttonBoxes.map((box) => box.top)).size).toBe(2);
    }
  });

  test("stage 1 Today and Assistant screenshots at required phone widths", async ({ page }, testInfo) => {
    for (const width of [360, 375, 393, 412, 430]) {
      await page.setViewportSize({ width, height: 844 });
      for (const [name, path] of [["today", "/today"], ["assistant", "/chat"]] as const) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await assertNoHorizontalScroll(page);
        await expect(page.locator('[data-surface] [data-surface]')).toHaveCount(0);
        const screenshotPath = `test-results/mobile-v1-${name}-${width}.png`;
        await page.screenshot({ path: screenshotPath, fullPage: true });
        await testInfo.attach(`mobile-v1-${name}-${width}`, {
          path: screenshotPath,
          contentType: "image/png",
        });
      }
    }
  });

  test("captures active task and next-event Today priorities", async ({ page }, testInfo) => {
    const activeTask = {
      kind: "task",
      id: "21111111-1111-4111-8111-111111111111",
      title: "撰写项目方案",
      start_at: "2026-07-20T05:00:00Z",
      end_at: "2026-07-20T06:00:00Z",
      status: "in_progress",
      due_at: null,
    };
    const nextEvent = {
      kind: "event",
      id: "11111111-1111-4111-8111-111111111111",
      title: "产品评审会议",
      start_at: "2026-07-20T07:00:00Z",
      end_at: "2026-07-20T08:00:00Z",
      status: null,
      due_at: null,
    };
    await page.route("**/api/v1/today/", (route) => route.fulfill({
      json: { ...emptyTodaySummary, execution_now: [activeTask], unfinished_tasks: [activeTask] },
    }));
    await page.setViewportSize({ width: 360, height: 844 });
    await page.goto("/today");
    await expect(page.getByTestId("today-focus")).toContainText("撰写项目方案");
    let screenshotPath = "test-results/mobile-v1-today-active-360.png";
    await page.screenshot({ path: screenshotPath, fullPage: true });
    await testInfo.attach("mobile-v1-today-active-360", { path: screenshotPath, contentType: "image/png" });

    await page.unroute("**/api/v1/today/");
    await page.route("**/api/v1/today/", (route) => route.fulfill({
      json: { ...emptyTodaySummary, execution_next: [nextEvent] },
    }));
    await page.setViewportSize({ width: 393, height: 844 });
    await page.goto("/today");
    await expect(page.getByTestId("today-focus")).toContainText("产品评审会议");
    screenshotPath = "test-results/mobile-v1-today-next-event-393.png";
    await page.screenshot({ path: screenshotPath, fullPage: true });
    await testInfo.attach("mobile-v1-today-next-event-393", { path: screenshotPath, contentType: "image/png" });
  });

  test("320 px reflow has no horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto("/today");
    await assertNoHorizontalScroll(page);
    await page.goto("/chat");
    await assertNoHorizontalScroll(page);
  });

  test("Today harvest stays flat while its text keeps strong contrast", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 844 });
    await page.goto("/today");
    const harvest = page.getByRole("region", { name: "今天收尾与明日草案" });
    const colors = await harvest.evaluate((section) => {
      const heading = section.querySelector(".text-amber-950");
      const description = section.querySelector(".text-sm.text-slate-600");
      return {
        background: getComputedStyle(section).backgroundColor,
        canvas: getComputedStyle(document.body).backgroundColor,
        heading: heading ? getComputedStyle(heading).color : "",
        description: description ? getComputedStyle(description).color : "",
      };
    });
    await expect(harvest).toHaveAttribute("data-surface", "none");
    expect(colors.background).toBe("rgba(0, 0, 0, 0)");
    expect(contrastRatio(colors.heading, colors.canvas)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(colors.description, colors.canvas)).toBeGreaterThanOrEqual(4.5);
  });

  test("Assistant history uses a modal drawer and the composer clears space for the keyboard", async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.goto("/chat");
    await page.getByRole("button", { name: "打开对话历史" }).click();
    await expect(page.getByRole("dialog", { name: "对话历史" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "对话历史" })).toHaveCount(0);

    await page.getByRole("textbox", { name: "消息" }).focus();
    await page.evaluate(() => {
      const viewport = window.visualViewport;
      if (!viewport) return;
      Object.defineProperty(viewport, "height", { configurable: true, value: window.innerHeight - 280 });
      viewport.dispatchEvent(new Event("resize"));
    });
    await expect(page.locator('nav[aria-label="移动端主导航"]')).toHaveAttribute("aria-hidden", "true");
    const composer = await page.getByRole("textbox", { name: "消息" }).boundingBox();
    const viewportHeight = await page.evaluate(() => window.innerHeight);
    expect(composer).not.toBeNull();
    await expect.poll(async () => {
      const box = await page.getByRole("textbox", { name: "消息" }).boundingBox();
      return box ? box.y + box.height : Number.POSITIVE_INFINITY;
    }).toBeLessThan(viewportHeight - 280);
  });

  test("chat composer reaches the keyboard edge when Android resizes the viewport", async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.goto("/chat");
    const composer = page.getByRole("textbox", { name: "消息" });
    const initialBottom = (await composer.boundingBox())!.y + (await composer.boundingBox())!.height;
    await composer.focus();
    await page.setViewportSize({ width: 393, height: 564 });
    await expect.poll(async () => {
      const box = await composer.boundingBox();
      return box ? box.y + box.height : Number.POSITIVE_INFINITY;
    }).toBeLessThanOrEqual(564);
    const updatedBottom = (await composer.boundingBox())!.y + (await composer.boundingBox())!.height;
    expect(564 - updatedBottom).toBeGreaterThanOrEqual(0);
    expect(564 - updatedBottom).toBeLessThanOrEqual(24);
    expect(updatedBottom).toBeGreaterThan(initialBottom - 200);
  });

  test("approval shows the planned change and primary action without horizontal overflow", async ({ page }) => {
    await page.route("**/api/v1/action-proposals/**", (route) => route.fulfill({ json: [{
      id: "41111111-1111-4111-8111-111111111111",
      conversation_id: "42222222-2222-4222-8222-222222222222",
      agent_run_id: "43333333-3333-4333-8333-333333333333",
      original_request: "明天安排项目评审",
      explanation: "这会在你的日历中新增一条安排。",
      action_type: "create_event",
      action_payload: { title: "项目评审", start_at: "2026-07-21T07:00:00Z", end_at: "2026-07-21T08:00:00Z" },
      original_payload: {},
      display_context: { allowed_decisions: ["approve", "edit", "reject"], object_name: "项目评审", proposed_start_at: "2026-07-21T07:00:00Z", proposed_end_at: "2026-07-21T08:00:00Z" },
      risk_level: "high",
      status: "awaiting_approval",
      requires_approval: true,
      version: 1,
      expires_at: "2026-07-21T06:00:00Z",
      decided_at: null,
      approved_at: null,
      resumed_at: null,
      executed_at: null,
      decision_reason: "",
      execution_result: null,
      error: "",
      created_at: "2026-07-20T02:00:00Z",
      updated_at: "2026-07-20T02:00:00Z",
    }] }));
    await page.goto("/approvals");
    await expect(page.getByText("将要改变")).toBeVisible();
    await expect(page.getByRole("button", { name: "确认并应用：项目评审" })).toBeVisible();
    await expect(page.getByRole("button", { name: "调整后批准：项目评审" })).toBeVisible();
    await expect(page.getByRole("button", { name: "拒绝：项目评审" })).toBeVisible();
    await expect(page.locator("article[data-surface='decision-surface']")).toHaveCount(1);
    await expect(page.locator("[data-surface] [data-surface]")).toHaveCount(0);
    await page.screenshot({ path: "../docs/mobile-ui/evidence/v2/approvals-393.png" });
    await assertNoHorizontalScroll(page);
  });

  test("approval filters use an accessible mobile drawer", async ({ page }) => {
    await page.route("**/api/v1/action-proposals/?status=awaiting_approval", (route) => route.fulfill({ json: [] }));
    await page.goto("/approvals");

    for (const width of [320, 360, 393]) {
      await page.setViewportSize({ width, height: 844 });
      const trigger = page.getByRole("button", { name: "状态：等待审批" });
      await trigger.click();
      const drawer = page.getByRole("dialog", { name: "筛选审批状态" });
      await expect(drawer).toBeVisible();
      for (const label of ["全部", "等待审批", "已执行", "已拒绝", "已过期", "执行失败"]) {
        const option = drawer.getByRole("button", { name: label, exact: true });
        await expect(option).toHaveAttribute("aria-pressed", String(label === "等待审批"));
        const box = await option.boundingBox();
        expect(box?.height).toBeGreaterThanOrEqual(44);
      }
      await expect(page.locator("body")).toHaveJSProperty("scrollWidth", width);
      if (width === 393) await page.screenshot({ path: "../docs/mobile-ui/evidence/iteration-3-approval-filter-393.png" });
      await page.keyboard.press("Escape");
      await expect(drawer).toHaveCount(0);
      await expect(trigger).toBeFocused();
    }
  });

  test("blocks a stale approval editor until it is reopened with the latest version", async ({ page }) => {
    await page.clock.install({ time: new Date("2026-10-04T12:00:00Z") });
    await page.setViewportSize({ width: 393, height: 844 });
    const id = "71111111-1111-4111-8111-111111111111";
    let latestProposal = {
      id,
      conversation_id: "72222222-2222-4222-8222-222222222222",
      agent_run_id: "73333333-3333-4333-8333-333333333333",
      original_request: "记得准备项目材料",
      explanation: "创建任务前需要确认内容。",
      action_type: "create_task_batch",
      action_payload: { tasks: [{ title: "旧任务", priority: "medium", estimated_minutes: 60 }] },
      original_payload: {},
      display_context: { allowed_decisions: ["approve", "edit", "reject"], review_complete: true, review_items: [{ title: "旧任务" }] },
      risk_level: "high",
      status: "awaiting_approval",
      requires_approval: true,
      version: 1,
      expires_at: "2026-10-05T12:00:00Z",
      decided_at: null,
      approved_at: null,
      resumed_at: null,
      executed_at: null,
      decision_reason: "",
      execution_result: null,
      error: "",
      created_at: "2026-10-04T08:00:00Z",
      updated_at: "2026-10-04T08:00:00Z",
    };
    const editBodies: Array<Record<string, unknown>> = [];
    await page.route("**/api/v1/action-proposals/**", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({ json: [latestProposal] });
        return;
      }
      const body = route.request().postDataJSON() as Record<string, unknown>;
      editBodies.push(body);
      await route.fulfill({ json: { proposal: { ...latestProposal, version: 3 }, resume_queued: false } });
    });
    await page.goto("/approvals");
    await page.getByRole("button", { name: /^调整后批准/ }).click();
    await page.getByRole("textbox", { name: "任务名称" }).fill("旧版本编辑");

    latestProposal = {
      ...latestProposal,
      version: 2,
      action_payload: { tasks: [{ title: "最新任务", priority: "high", estimated_minutes: 90 }] },
      display_context: { ...latestProposal.display_context, review_items: [{ title: "最新任务" }] },
    };
    await page.clock.fastForward("00:00:16");
    await expect(page.getByRole("alert").filter({ hasText: "旧内容不会提交" })).toBeVisible();
    await expect(page.getByRole("button", { name: /^保存修改并批准/ })).toBeDisabled();
    expect(editBodies).toHaveLength(0);

    await page.getByRole("button", { name: "取消编辑" }).click();
    await page.getByRole("button", { name: /^调整后批准/ }).click();
    const taskName = page.getByRole("textbox", { name: "任务名称" });
    await expect(taskName).toHaveValue("最新任务");
    await taskName.fill("重新编辑");
    await page.getByRole("button", { name: /^保存修改并批准/ }).click();
    await expect.poll(() => editBodies.length).toBe(1);
    expect(editBodies[0]).toMatchObject({ expected_version: 2, action_payload: { tasks: [{ title: "重新编辑", priority: "high", estimated_minutes: 90 }] } });
  });

  test("reminder creation uses a mobile sheet and keeps account-local time", async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    let requestBody: Record<string, unknown> | undefined;
    await page.route("**/api/v1/reminders/**", async (route) => {
      if (route.request().method() === "POST") {
        requestBody = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({ status: 201, json: {
          id: "81111111-1111-4111-8111-111111111111", target_type: "custom", target_id: null,
          title: String(requestBody.title), trigger_at: String(requestBody.trigger_at), timezone: String(requestBody.timezone),
          channel: "console", status: "pending", deduplication_key: requestBody.deduplication_key,
          queued_at: null, sent_at: null, retry_count: 0, failure_reason: "", created_at: "2026-10-04T00:00:00Z", updated_at: "2026-10-04T00:00:00Z",
        } });
        return;
      }
      await route.fulfill({ json: [] });
    });
    await page.goto("/reminders");
    await page.getByRole("button", { name: "打开新建提醒" }).click();
    const drawer = page.getByRole("dialog", { name: "新建提醒" });
    await expect(drawer).toBeVisible();
    const drawerBounds = await drawer.boundingBox();
    expect(drawerBounds?.height).toBeLessThan(700);
    for (const width of [320, 360, 393, 430]) {
      await page.setViewportSize({ width, height: 844 });
      await expect(page.locator("body")).toHaveJSProperty("scrollWidth", width);
      if (width === 393) await page.screenshot({ path: "../docs/mobile-ui/evidence/v2/reminder-create-393.png" });
    }
    await page.setViewportSize({ width: 393, height: 844 });
    await page.getByLabel("提醒内容").fill("提交项目报告");
    await page.getByLabel(/提醒时间/).fill("2026-10-05T18:30");
    await page.getByRole("button", { name: "创建提醒" }).click();

    await expect.poll(() => requestBody).toMatchObject({
      title: "提交项目报告",
      trigger_at: "2026-10-05T10:30:00.000Z",
      timezone: "Asia/Shanghai",
      target_type: "custom",
    });
    await expect(page.getByRole("status").filter({ hasText: "提醒已创建" })).toBeVisible();
    await expect(drawer).toHaveCount(0);
  });

  test("keeps V2 reminder records in status groups and divider rows", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 393, height: 844 });
    const reminder = (id: string, title: string, status: string, triggerAt: string) => ({
      id,
      target_type: "custom",
      target_id: null,
      title,
      trigger_at: triggerAt,
      timezone: "Asia/Shanghai",
      channel: "console",
      status,
      deduplication_key: `mobile-v2-${id}`,
      queued_at: null,
      sent_at: status === "sent" ? "2026-10-04T04:00:00Z" : null,
      retry_count: status === "failed" ? 2 : 0,
      failure_reason: status === "failed" ? "连接暂时不可用" : "",
      created_at: "2026-10-04T00:00:00Z",
      updated_at: "2026-10-04T00:00:00Z",
    });
    await page.route("**/api/v1/reminders/**", (route) => route.fulfill({ json: [
      reminder("reminder-pending", "提交项目报告", "pending", "2026-10-05T10:30:00Z"),
      reminder("reminder-failed", "确认会议材料", "failed", "2026-10-05T08:00:00Z"),
      reminder("reminder-sent", "准备周报", "sent", "2026-10-04T04:00:00Z"),
      reminder("reminder-cancelled", "旧提醒", "cancelled", "2026-10-03T04:00:00Z"),
    ] }));
    await page.goto("/reminders");
    await expect(page.getByRole("heading", { name: "提醒" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "需要处理" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "待发送" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "提醒记录" })).toBeVisible();
    await expect(page.locator('[data-surface="divider-list"]')).toHaveCount(4);
    await expect(page.locator('[data-surface] [data-surface]')).toHaveCount(0);
    const screenshotPath = "../docs/mobile-ui/evidence/v2/reminders-list-393.png";
    await page.screenshot({ path: screenshotPath, fullPage: true });
    await testInfo.attach("v2-reminders-list-393", { path: screenshotPath, contentType: "image/png" });

    await page.locator("summary").filter({ hasText: "已取消" }).click();
    await expect(page.getByText("旧提醒")).toBeVisible();
  });

  test("memory proposals show a readable value and confirmation reason", async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.route("**/api/v1/time-memory/me/", (route) => route.fulfill({ json: { profile: null, refresh_status: "clean", dirty_at: null, last_completed_at: null, last_error: "" } }));
    await page.route("**/api/v1/time-memory/me/decision-profile/", (route) => route.fulfill({ json: { duration_multiplier: 1, sample_count: 0, confidence: 0, evidence: [], source: "default" } }));
    await page.route("**/api/v1/time-memory/me/semantic/", (route) => route.fulfill({ json: [] }));
    await page.route("**/api/v1/time-memory/me/proposals/recent/", (route) => route.fulfill({ json: [{
      id: "92222222-2222-4222-8222-222222222222", operation: "create", category: "scheduling_preference", key: "focus_period",
      value: { period: "morning" }, confidence: 0.9, reason_code: "explicit_low_risk_direct_apply", policy_reason: "explicit",
      status: "applied", source_run_id: null, source_type: "conversation", target_memory_id: null, target_version: null,
      applied_memory_id: "93333333-3333-4333-8333-333333333333", applied_memory_version: 1, changed_business_state: true,
      can_undo: true, undone_at: null, created_at: "2026-10-04T00:00:00Z", updated_at: "2026-10-04T00:00:00Z",
    }] }));
    await page.route("**/api/v1/time-memory/me/proposals/", (route) => route.fulfill({ json: [{
      id: "91111111-1111-4111-8111-111111111111", operation: "create", category: "scheduling_preference", key: "focus_period",
      value: { period: "morning" }, confidence: 0.8, reason_code: "user_confirmation_required", policy_reason: "confirmation",
      status: "pending", source_run_id: null, source_type: "conversation", target_memory_id: null, target_version: null,
      applied_memory_id: null, applied_memory_version: null, changed_business_state: false, can_undo: false, undone_at: null,
      created_at: "2026-10-04T00:00:00Z", updated_at: "2026-10-04T00:00:00Z",
    }] }));
    await page.goto("/settings/time-memory");

    await expect(page.getByText("专注时段", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("时段：上午")).toBeVisible();
    await expect(page.getByText(/这项偏好由系统推断/)).toBeVisible();
    await expect(page.getByText(/已生效 · 2026年10月4日 08:00/)).toBeVisible();
    await expect(page.getByText("user_confirmation_required")).toHaveCount(0);
    for (const width of [360, 393, 430]) {
      await page.setViewportSize({ width, height: 844 });
      await expect(page.locator("body")).toHaveJSProperty("scrollWidth", width);
      await page.screenshot({ path: `../docs/mobile-ui/evidence/iteration-3-memory-${width}.png` });
    }
    await page.setViewportSize({ width: 393, height: 844 });
    await page.getByRole("heading", { name: "用户表达的偏好" }).evaluate((element) => element.scrollIntoView({ block: "start" }));
    await page.screenshot({ path: "../docs/mobile-ui/evidence/iteration-3-memory-proposals-393.png" });
  });

  test("mobile month grid renders six navigable weeks and full date names", async ({ page }) => {
    await page.goto("/calendar");
    const grid = page.getByRole("grid", { name: "选择日期" });
    await expect(grid.getByRole("gridcell")).toHaveCount(42);
    await expect(grid.locator('button[tabindex="0"]')).toHaveAttribute("aria-label", /202\d年.*月.*日/);
    await expect(page.getByRole("button", { name: "上个月" })).toBeVisible();
    await expect(page.getByRole("button", { name: "下个月" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "周" })).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "日" })).toHaveCount(0);
  });

  test("calendar date grid supports keyboard selection and restores focus from agenda", async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.route("**/api/v1/events/**", (route) => route.fulfill({ json: [{
      id: "11111111-1111-4111-8111-111111111111",
      title: "键盘日程",
      start_at: "2026-10-05T02:00:00Z",
      end_at: "2026-10-05T03:00:00Z",
      timezone: "Asia/Shanghai",
      location: "会议室 A",
      status: "confirmed",
      visibility: "private",
      source: "local",
      version: 1,
    }] }));
    await page.goto("/calendar?date=2026-10-05");
    const grid = page.getByRole("grid", { name: "选择日期" });
    const dateButton = grid.getByRole("button", { name: /2026年10月5日/ });
    await dateButton.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog", { name: /2026年10月5日/ })).toBeVisible();
    await expect(page.getByRole("dialog").getByRole("heading", { name: "键盘日程" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: /2026年10月5日/ })).toHaveCount(0);
    await expect(dateButton).toBeFocused();
  });

  test("uses a floating create action on the mobile calendar", async ({ page }) => {
    await page.goto("/calendar");
    await expect(page.getByRole("button", { name: "快速新建日程" })).toBeVisible();
  });

  test("selected controls keep contrast and primary mobile targets meet size", async ({ page }) => {
    const calendarEvent = {
      id: "11111111-1111-4111-8111-111111111111",
      title: "可访问性评审",
      start_at: "2026-10-05T02:00:00Z",
      end_at: "2026-10-05T03:00:00Z",
      timezone: "Asia/Shanghai",
      location: "会议室 A",
      status: "confirmed",
      visibility: "private",
      source: "local",
      version: 1,
    };
    const task = {
      id: "21111111-1111-4111-8111-111111111111",
      project: "移动端",
      parent_task: null,
      title: "检查触控目标",
      description: "验证手机端任务操作",
      status: "pending",
      priority: "high",
      due_at: "2026-10-06T10:00:00Z",
      estimated_minutes: 30,
      planned_start_at: null,
      planned_end_at: null,
      actual_started_at: null,
      completed_at: null,
      source: "local",
      tags: ["验收"],
      created_at: "2026-10-01T01:00:00Z",
      updated_at: "2026-10-01T01:00:00Z",
    };
    await page.setViewportSize({ width: 360, height: 844 });
    await page.goto("/schedule");
    const selectedHubDate = page.getByRole("group", { name: "本周日期" })
      .getByRole("button", { pressed: true });
    const hubDateBox = await selectedHubDate.boundingBox();
    expect(hubDateBox?.height).toBeGreaterThanOrEqual(48);
    const hubColors = await selectedHubDate.evaluate((element) => ({
      foreground: getComputedStyle(element).color,
      background: getComputedStyle(element).backgroundColor,
    }));
    expect(contrastRatio(hubColors.foreground, hubColors.background)).toBeGreaterThanOrEqual(4.5);

    await page.route("**/api/v1/events/**", (route) => route.fulfill({ json: [calendarEvent] }));
    await page.goto("/calendar?date=2026-10-05");
    const grid = page.getByRole("grid", { name: "选择日期" });
    const selectedCalendarDate = grid.getByRole("button", { name: /2026年10月5日/ });
    const dateBox = await selectedCalendarDate.boundingBox();
    expect(dateBox?.height).toBeGreaterThanOrEqual(48);
    expect(dateBox?.width).toBeGreaterThanOrEqual(44);
    const calendarColors = await selectedCalendarDate.evaluate((element) => ({
      foreground: getComputedStyle(element).color,
      background: getComputedStyle(element).backgroundColor,
    }));
    expect(contrastRatio(calendarColors.foreground, calendarColors.background)).toBeGreaterThanOrEqual(4.5);
    await selectedCalendarDate.click();
    const agenda = page.getByRole("dialog", { name: /2026年10月5日/ });
    await expect(agenda).toBeVisible();
    for (const name of ["修改", "删除", "在这一天新建日程"]) {
      const button = agenda.getByRole("button", { name });
      const box = await button.boundingBox();
      expect(box?.height, name).toBeGreaterThanOrEqual(44);
    }

    await page.route("**/api/v1/tasks/**", (route) => route.fulfill({ json: [task] }));
    await page.goto("/tasks");
    const inbox = page.getByRole("button", { name: "收件箱" });
    await expect(page.getByText("检查触控目标")).toBeVisible();
    const filterBox = await inbox.boundingBox();
    expect(filterBox?.height).toBeGreaterThanOrEqual(44);
    const filterColors = await inbox.evaluate((element) => ({
      foreground: getComputedStyle(element).color,
      background: getComputedStyle(element).backgroundColor,
    }));
    expect(contrastRatio(filterColors.foreground, filterColors.background)).toBeGreaterThanOrEqual(4.5);
    const start = page.getByRole("button", { name: "开始任务：检查触控目标" });
    const startBox = await start.boundingBox();
    expect(startBox?.height).toBeGreaterThanOrEqual(48);
    const more = page.getByText("更多操作", { exact: true });
    await more.click();
    const edit = page.getByRole("button", { name: "编辑任务：检查触控目标" });
    const editBox = await edit.boundingBox();
    expect(editBox?.height).toBeGreaterThanOrEqual(44);
  });

  test("Plan tab opens the Schedule Hub and links into task, calendar, and planning routes", async ({ page }) => {
    await page.goto("/today");
    await page.getByRole("link", { name: /计划/ }).click();
    await expect(page).toHaveURL(/\/schedule$/);
    await expect(page.getByRole("heading", { name: "计划" })).toBeVisible();
    await expect(page.getByRole("link", { name: /^日历$/ })).toBeVisible();
    await expect(page.getByRole("link", { name: "全部任务" })).toHaveAttribute("href", "/tasks");
    await expect(page.getByRole("link", { name: "让助理起草安排" })).toHaveAttribute("href", "/planning");
  });

  test("captures mobile page screenshots", async ({ page }, testInfo) => {
    for (const [name, path] of [
      ["today", "/today"],
      ["chat", "/chat"],
      ["schedule", "/schedule"],
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

  test("saves populated Plan, Calendar, and Tasks screenshots at all target widths", async ({ page }, testInfo) => {
    const calendarEvent = {
      id: "11111111-1111-4111-8111-111111111111",
      title: "产品评审会议",
      start_at: "2026-10-05T02:00:00Z",
      end_at: "2026-10-05T03:00:00Z",
      timezone: "Asia/Shanghai",
      location: "会议室 A",
      status: "confirmed",
      visibility: "private",
      source: "local",
      version: 1,
    };
    const todayEvent = {
      ...calendarEvent,
      id: "12222222-2222-4222-8222-222222222222",
      title: "今日复盘",
      start_at: "2026-10-04T02:00:00Z",
      end_at: "2026-10-04T02:30:00Z",
    };
    const plannedTask = {
      id: "21111111-1111-4111-8111-111111111111",
      project: "产品发布",
      parent_task: null,
      title: "准备评审材料",
      description: "整理决策和风险",
      status: "pending",
      priority: "high",
      due_at: "2026-10-06T10:00:00Z",
      estimated_minutes: 60,
      planned_start_at: "2026-10-04T04:00:00Z",
      planned_end_at: "2026-10-04T05:00:00Z",
      actual_started_at: null,
      completed_at: null,
      source: "local",
      tags: ["工作", "项目"],
      created_at: "2026-10-01T01:00:00Z",
      updated_at: "2026-10-01T01:00:00Z",
    };
    const unplannedTask = {
      ...plannedTask,
      id: "31111111-1111-4111-8111-111111111111",
      title: "整理会议结论",
      planned_start_at: null,
      planned_end_at: null,
    };
    const nextDayTask = {
      ...plannedTask,
      id: "22222222-2222-4222-8222-222222222222",
      title: "整理评审材料",
      planned_start_at: "2026-10-05T04:00:00Z",
      planned_end_at: "2026-10-05T05:00:00Z",
    };
    await page.route("**/api/v1/events/**", (route) => route.fulfill({ json: [todayEvent, calendarEvent] }));
    await page.route("**/api/v1/tasks/**", (route) => route.fulfill({ json: [plannedTask, nextDayTask, unplannedTask] }));

    for (const width of [320, 360, 375, 393, 412, 430]) {
      await page.setViewportSize({ width, height: 844 });
      for (const [name, path] of [
        ["plan", "/schedule"],
        ["calendar", "/calendar?date=2026-10-05"],
        ["tasks", "/tasks"],
      ] as const) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await assertNoHorizontalScroll(page);
        if (width === 320 && name === "plan") {
          const dateRail = page.getByRole("group", { name: "本周日期" });
          const monday = dateRail.getByRole("button").first();
          const target = await monday.boundingBox();
          const primaryAction = await page.getByRole("link", { name: "让助理起草安排" }).boundingBox();
          const bottomNavigation = await page.getByRole("navigation", { name: "移动端主导航" }).boundingBox();
          expect(target?.width).toBeGreaterThanOrEqual(44);
          expect(target?.height).toBeGreaterThanOrEqual(44);
          if (!primaryAction || !bottomNavigation) throw new Error("Plan primary action or bottom navigation is not visible");
          expect(primaryAction.y + primaryAction.height).toBeLessThanOrEqual(bottomNavigation.y);
          expect(page.getByText("左右滑动可查看其余日期")).toBeVisible();
          expect(await dateRail.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
        }
        if (width === 393 && name === "tasks") {
          const moreActions = page.locator('summary[aria-label^="更多操作："]').first();
          await expect(moreActions).toBeVisible();
          await expect(moreActions).toHaveAttribute("aria-label", /更多操作：.+/);
        }
        const imagePath = `../docs/mobile-ui/evidence/v2/${name}-${width}.png`;
        await page.screenshot({ path: imagePath, fullPage: true });
        await testInfo.attach(`v2-${name}-${width}`, { path: imagePath, contentType: "image/png" });
      }
    }

    await page.setViewportSize({ width: 393, height: 844 });
    await page.goto("/calendar?date=2026-10-05");
    await page.getByRole("grid", { name: "选择日期" }).getByRole("button", { name: /2026年10月5日/ }).click();
    await expect(page.getByRole("dialog", { name: /2026年10月5日/ })).toBeVisible();
    const sheetPath = "../docs/mobile-ui/evidence/v2/calendar-agenda-393.png";
    await page.screenshot({ path: sheetPath, fullPage: true });
    await testInfo.attach("v2-calendar-agenda-393", { path: sheetPath, contentType: "image/png" });
  });

  test("captures the V2 Today focus, alert, and harvest hierarchy", async ({ page }, testInfo) => {
    const dueAt = "2026-10-02T15:45:00+00:00";
    let showActiveAndAlert = true;
    await page.setViewportSize({ width: 393, height: 844 });
    await page.route("**/api/v1/today/", (route) => route.fulfill({
      json: showActiveAndAlert ? {
        ...emptyTodaySummary,
        completed_tasks: [{ id: "completed-1", title: "完成周度复盘" }],
        execution_next: [{
          kind: "task",
          id: "focus-1",
          title: "准备产品评审材料",
          start_at: "2026-10-05T02:00:00Z",
          end_at: "2026-10-05T03:00:00Z",
          status: "pending",
          due_at: null,
        }],
      } : emptyTodaySummary,
    }));
    await page.route("**/api/v1/insights/", (route) => route.fulfill({
      json: showActiveAndAlert ? [{
        id: "insight-1",
        kind: "task_overdue",
        severity: "warning",
        status: "open",
        title: "一项任务已经逾期",
        summary: "请检查是否需要调整后续安排。",
        evidence: { due_at: dueAt },
        deduplication_key: "mobile-v2-overdue",
        detected_at: "2026-10-05T02:00:00Z",
        expires_at: "2026-10-06T02:00:00Z",
      }] : [],
    }));

    await page.goto("/today");
    const alert = page.getByRole("region", { name: "需要留意" });
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("截止：");
    await expect(alert).not.toContainText(dueAt);
    await expect(page.getByTestId("today-focus")).toContainText("准备产品评审材料");
    await expect(page.getByRole("heading", { name: "今日收获" })).toBeVisible();
    await expect(page.getByText("完成周度复盘")).toBeVisible();
    await expect(page.locator('[data-surface] [data-surface]')).toHaveCount(0);

    const imagePath = "../docs/mobile-ui/evidence/v2/today-393.png";
    await page.screenshot({ path: imagePath, fullPage: true });
    await testInfo.attach("v2-today-393", { path: imagePath, contentType: "image/png" });

    showActiveAndAlert = false;
    await page.reload();
    await expect(page.getByText("今天还没有完成任务")).toBeVisible();
    await expect(page.getByRole("heading", { name: "今日收获" })).toBeVisible();
    const emptyImagePath = "../docs/mobile-ui/evidence/v2/today-empty-393.png";
    await page.screenshot({ path: emptyImagePath, fullPage: true });
    await testInfo.attach("v2-today-empty-393", { path: emptyImagePath, contentType: "image/png" });
  });
});
