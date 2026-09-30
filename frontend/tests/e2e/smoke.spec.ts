import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("time-agent:onboarding:1:v1", "completed");
  });
  await page.route("**/api/v1/auth/me/", async (route) => {
    await route.fulfill({
      json: { id: 1, email: "e2e@example.test", display_name: "E2E User", is_staff: false },
    });
  });
  await page.route("**/api/v1/auth/csrf/", async (route) => {
    await route.fulfill({ json: { csrfToken: "e2e-csrf" } });
  });
  await page.route("**/api/v1/auth/options/", async (route) => {
    await route.fulfill({ json: { guest_access_enabled: false, registration_enabled: true } });
  });
  await page.route("**/api/v1/insights/", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/integrations/calendar/connections/", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/briefings/evening-preview/", (route) =>
    route.fulfill({
      json: {
        target_date: "2026-08-24",
        timezone: "Asia/Shanghai",
        generated_at: "2026-08-24T12:00:00Z",
        events: [],
        tasks: [],
        insights: [],
        warnings: [],
      },
    }),
  );
});

test("redirects an unauthenticated visitor to the login page", async ({ page }) => {
  await page.unroute("**/api/v1/auth/me/");
  await page.route("**/api/v1/auth/me/", async (route) => {
    await route.fulfill({ status: 401, json: { detail: "Authentication credentials were not provided." } });
  });

  await page.goto("/today");

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "登录 Time Agent" })).toBeVisible();
});

test("shows registration and hides guest access when backend options disable guests", async ({ page }) => {
  await page.goto("/login");

  await expect(page.getByRole("tab", { name: "注册" })).toBeVisible();
  await expect(page.getByRole("button", { name: "游客体验（无需注册）" })).toHaveCount(0);
  const loginTab = page.getByRole("tab", { name: "登录" });
  const registerTab = page.getByRole("tab", { name: "注册" });
  await loginTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(registerTab).toBeFocused();
  await expect(registerTab).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "创建账号" })).toBeVisible();
});

test("keeps registration available and retryable when account options are unavailable", async ({ page }) => {
  let requestCount = 0;
  await page.unroute("**/api/v1/auth/options/");
  await page.route("**/api/v1/auth/options/", async (route) => {
    requestCount += 1;
    await route.fulfill({ status: 503, json: { detail: "Unavailable" } });
  });
  await page.setViewportSize({ width: 320, height: 700 });

  await page.goto("/login");

  await expect(page.getByText("暂时无法确认注册状态；游客体验已隐藏。你仍可登录或尝试注册。")).toBeVisible();
  await expect(page.getByRole("tab", { name: "注册" })).toBeVisible();
  await expect(page.getByRole("button", { name: "游客体验（无需注册）" })).toHaveCount(0);
  const retryButton = page.getByRole("button", { name: "重试" });
  const retryBounds = await retryButton.boundingBox();
  expect(retryBounds?.height).toBeGreaterThanOrEqual(44);
  expect(retryBounds?.width).toBeGreaterThanOrEqual(44);
  const initialRequestCount = requestCount;
  await retryButton.click();
  await expect.poll(() => requestCount).toBeGreaterThan(initialRequestCount);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test("returns focus to the account panel after auth options recover", async ({ page }) => {
  let optionsAvailable = false;
  await page.unroute("**/api/v1/auth/options/");
  await page.route("**/api/v1/auth/options/", async (route) => {
    if (optionsAvailable) {
      await route.fulfill({ json: { guest_access_enabled: false, registration_enabled: true } });
      return;
    }
    await route.fulfill({ status: 503, json: { detail: "Unavailable" } });
  });

  await page.goto("/login");
  await expect(page.getByRole("button", { name: "重试" })).toBeVisible();
  optionsAvailable = true;
  await page.getByRole("button", { name: "重试" }).click();

  await expect(page.getByText("账号选项已重新读取。")).toBeVisible();
  await expect(page.getByRole("tabpanel")).toBeFocused();
});

test("logs in from the dedicated login page", async ({ page }) => {
  await page.route("**/api/v1/auth/login/", async (route) => {
    await route.fulfill({
      json: { id: 1, email: "e2e@example.test", display_name: "E2E User", is_staff: false },
    });
  });
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({
      json: {
        timezone: "Asia/Shanghai", locale: "zh-CN", workday_start: "09:00:00", workday_end: "18:00:00",
        sleep_start: "23:00:00", sleep_end: "07:00:00", default_event_duration_minutes: 60,
        preferred_focus_periods: [], default_reminder_offsets: [], weather_location: "", news_topics: [],
        briefing_time: "08:00:00", planning_rules: {}, updated_at: "2026-07-17T00:00:00Z",
      },
    });
  });

  await page.goto("/login");
  await page.getByLabel("邮箱").fill("e2e@example.test");
  await page.getByLabel("密码").fill("strong password 123");
  await page.getByRole("button", { name: "登录", exact: true }).last().click();

  await expect(page).toHaveURL(/\/today$/);
});

test("renders the system status shell", async ({ page }) => {
  await page.unroute("**/api/v1/auth/me/");
  await page.route("**/api/v1/auth/me/", async (route) => {
    await route.fulfill({
      json: { id: 1, email: "admin@example.test", display_name: "E2E Admin", is_staff: true },
    });
  });
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({
      json: {
        timezone: "Asia/Shanghai", locale: "zh-CN", workday_start: "09:00:00", workday_end: "18:00:00",
        sleep_start: "23:00:00", sleep_end: "07:00:00", default_event_duration_minutes: 60,
        preferred_focus_periods: [], default_reminder_offsets: [], weather_location: "", news_topics: [],
        briefing_time: "08:00:00", planning_rules: {}, updated_at: "2026-07-17T00:00:00Z",
      },
    });
  });
  await page.route("**/health/ready", async (route) => {
    await route.fulfill({
      json: { status: "ready", checks: { database: "ok", redis: "ok" } },
    });
  });

  await page.goto("/system-status");
  await expect(page.getByRole("heading", { name: "系统状态" })).toBeVisible();
});

test("uses the mobile app shell below the desktop breakpoint", async ({ page }) => {
  await page.setViewportSize({ width: 930, height: 1000 });
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({
      json: {
        timezone: "Asia/Shanghai", locale: "zh-CN", workday_start: "09:00:00", workday_end: "18:00:00",
        sleep_start: "23:00:00", sleep_end: "07:00:00", default_event_duration_minutes: 60,
        preferred_focus_periods: [], default_reminder_offsets: [], weather_location: "", news_topics: [],
        briefing_time: "08:00:00", planning_rules: {}, updated_at: "2026-07-17T00:00:00Z",
      },
    });
  });
  await page.route("**/api/v1/tasks/**", async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/tasks");

  await expect(page.getByTestId("desktop-sidebar")).toBeHidden();
  await expect(page.getByRole("navigation", { name: "移动端主导航" })).toBeVisible();
  await expect(page.getByRole("button", { name: "更多" })).toBeVisible();
  // Mobile hides the giant 任务 heading; the workspace tab bar carries the label.
  await expect(page.getByRole("navigation", { name: "时间管理工作区" })).toBeVisible();
  await expect(page.getByRole("link", { name: "任务" })).toBeVisible();
});

test("records a task action and shows plan-versus-actual evidence", async ({ page }) => {
  const taskId = "21111111-1111-4111-8111-111111111111";
  let status = "pending";
  await page.addInitScript(() =>
    localStorage.setItem("time-agent:onboarding:1:v1", "completed"),
  );
  await page.route("**/api/v1/preferences/me/", (route) =>
    route.fulfill({ json: { timezone: "Asia/Shanghai", locale: "zh-CN" } }),
  );
  await page.route(`**/api/v1/tasks/${taskId}/execution-signals/`, async (route) => {
    status = "in_progress";
    await route.fulfill({
      json: {
        id: "41111111-1111-4111-8111-111111111111",
        task: taskId,
        signal_type: "started",
        occurred_at: "2026-08-24T09:00:00Z",
        idempotency_key: "e2e-start",
        source: "web",
        metadata: {},
        created_at: "2026-08-24T09:00:00Z",
      },
    });
  });
  await page.route(`**/api/v1/tasks/${taskId}/execution-summary/`, (route) =>
    route.fulfill({
      json: {
        task_id: taskId,
        signal_count: 2,
        active_seconds: 2100,
        planned_seconds: 2700,
        estimated_seconds: 1800,
        variance_vs_plan_seconds: -600,
        variance_vs_estimate_seconds: 300,
        evidence_status: "complete",
        open_started_at: null,
        last_signal_type: "paused",
      },
    }),
  );
  await page.route("**/api/v1/tasks/**", (route) => {
    if (!route.request().url().endsWith("/api/v1/tasks/")) return route.fallback();
    return route.fulfill({
      json: [
        {
          id: taskId,
          project: "E2E",
          parent_task: null,
          title: "准备发布报告",
          description: "",
          status,
          priority: "high",
          due_at: "2026-08-25T10:00:00Z",
          estimated_minutes: 30,
          planned_start_at: "2026-08-24T09:00:00Z",
          planned_end_at: "2026-08-24T09:45:00Z",
          actual_started_at: status === "in_progress" ? "2026-08-24T09:00:00Z" : null,
          completed_at: null,
          source: "local",
          tags: [],
          version: status === "in_progress" ? 2 : 1,
          created_at: "2026-08-23T09:00:00Z",
          updated_at: "2026-08-24T09:00:00Z",
        },
      ],
    });
  });

  await page.goto("/tasks");
  await page.getByText("更多筛选").click();
  await page.getByRole("button", { name: "已计划" }).click();
  await page.getByRole("button", { name: "开始任务：准备发布报告" }).click();
  await expect(page.getByRole("button", { name: "暂停任务：准备发布报告" })).toBeVisible();
  await page.getByRole("button", { name: "查看执行摘要：准备发布报告" }).click();
  await expect(page.getByText("相对计划块 -10 分钟")).toBeVisible();
  await expect(page.getByText("相对估时 5 分钟")).toBeVisible();
});

test("reviews and applies a deterministic schedule plan", async ({ page }) => {
  const taskId = "21111111-1111-4111-8111-111111111111";
  const planId = "41111111-1111-4111-8111-111111111111";
  await page.clock.install({ time: new Date("2026-08-24T01:00:00Z") });
  await page.addInitScript(() =>
    localStorage.setItem("time-agent:onboarding:1:v1", "completed"),
  );
  await page.route("**/api/v1/preferences/me/", (route) =>
    route.fulfill({ json: { timezone: "Asia/Shanghai", locale: "zh-CN" } }),
  );
  await page.route("**/api/v1/tasks/", (route) => route.fulfill({
    json: [{
      id: taskId,
      project: "E2E",
      parent_task: null,
      title: "准备规划演示",
      description: "",
      status: "pending",
      priority: "high",
      due_at: "2026-08-26T10:00:00Z",
      estimated_minutes: 60,
      planned_start_at: null,
      planned_end_at: null,
      actual_started_at: null,
      completed_at: null,
      source: "local",
      tags: [],
      version: 1,
      created_at: "2026-08-23T09:00:00Z",
      updated_at: "2026-08-23T09:00:00Z",
    }],
  }));
  await page.route("**/api/v1/planning/automation-policies/", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/time-memory/me/capacity-forecast/**", (route) =>
    route.fulfill({
      json: {
        range_start: "2026-08-24T01:00:00Z",
        range_end: "2026-08-31T01:00:00Z",
        available_minutes: 480,
        committed_minutes: 120,
        unplanned_minutes: 600,
        risk: "over_capacity",
        reason_codes: ["unplanned_exceeds_free_capacity"],
      },
    }),
  );
  await page.route("**/api/v1/planning/plans/", async (route) => {
    await route.fulfill({
      status: 201,
      json: {
        id: planId,
        strategy: "plan_tasks_only",
        status: "draft",
        version: 1,
        created_at: "2026-08-24T09:00:00Z",
        updated_at: "2026-08-24T09:00:00Z",
        expires_at: "2026-08-24T10:00:00Z",
        applied_at: null,
        items: [{
          task_id: taskId,
          task_version: 1,
          state: "placed",
          start_at: "2026-08-25T01:00:00Z",
          end_at: "2026-08-25T02:00:00Z",
          locked: false,
          reason_codes: [],
        }],
      },
    });
  });
  await page.route(`**/api/v1/planning/plans/${planId}/apply/`, async (route) => {
    await route.fulfill({
      json: {
        id: planId,
        strategy: "plan_tasks_only",
        status: "applied",
        version: 2,
        created_at: "2026-08-24T09:00:00Z",
        applied_at: "2026-08-24T09:01:00Z",
        items: [],
      },
    });
  });

  await page.goto("/planning");
  await expect(page.getByText("容量超载")).toBeVisible();
  await page.getByRole("button", { name: "高级规划设置" }).click();
  await expect(page.getByRole("checkbox", { name: /准备规划演示/ })).toBeChecked();
  await page.getByRole("button", { name: "生成草案" }).click();
  const planPreview = page.getByRole("region", { name: "计划时间线" });
  await expect(planPreview).toBeVisible();
  await expect(planPreview.getByText("准备规划演示")).toBeVisible();
  await page.getByRole("button", { name: "应用计划" }).click();
  await expect(page.getByText("计划已应用。")).toBeVisible();
});

test("reads and updates time preferences", async ({ page }) => {
  let timezone = "Asia/Shanghai";
  let weatherLocation = "";
  let newsTopics: string[] = [];
  await page.route("**/api/v1/providers/catalog/", async (route) => {
    await route.fulfill({
      json: {
        weather_provider: "Open-Meteo",
        news_provider: "RSS",
        news_feeds: [],
        topic_aliases: {},
        news_topics: ["AI", "Python"],
        timezones: ["Asia/Shanghai"],
        locales: ["zh-CN", "en-US"],
      },
    });
  });
  await page.route("**/api/v1/providers/locations/administrative-areas/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("city_code") === "340100") {
      await route.fulfill({ json: [{ code: "340103", name: "庐阳区" }] });
      return;
    }
    if (url.searchParams.get("province_code") === "340000") {
      await route.fulfill({ json: [{ code: "340100", name: "合肥市" }] });
      return;
    }
    await route.fulfill({ json: [{ code: "340000", name: "安徽省" }] });
  });
  await page.route("**/api/v1/providers/locations/resolve/**", async (route) => {
    await route.fulfill({
      json: {
        provider: "open_meteo",
        provider_location_id: "e2e-hefei",
        name: "庐阳区",
        admin1: "安徽省",
        country: "中国",
        timezone: "Asia/Shanghai",
        label: "安徽省 / 合肥市 / 庐阳区",
        latitude: 31.88,
        longitude: 117.26,
        province: "安徽省",
        city: "合肥市",
        district: "庐阳区",
      },
    });
  });
  await page.route("**/api/v1/preferences/me/", async (route) => {
    if (route.request().method() === "PATCH") {
      const changes = route.request().postDataJSON() as {
        timezone: string;
        weather_location: string;
        news_topics: string[];
      };
      timezone = changes.timezone;
      weatherLocation = changes.weather_location;
      newsTopics = changes.news_topics;
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
        weather_location: weatherLocation,
        news_topics: newsTopics,
        briefing_time: "08:00:00",
        planning_rules: {},
        updated_at: "2026-07-17T00:00:00Z",
      },
    });
  });

  await page.goto("/settings/time");
  await expect(page.getByRole("heading", { name: "偏好设置" })).toBeVisible();
  const skipTour = page.getByRole("button", { name: "暂时跳过" });
  if (await skipTour.isVisible()) await skipTour.click();
  await page.getByLabel("IANA 时区").selectOption("Asia/Shanghai");
  await page.getByLabel("省").selectOption("340000");
  await page.getByLabel("市").selectOption("340100");
  await page.getByLabel("区 / 县").selectOption("340103");
  await expect(page.getByText("文字标签：安徽省 / 合肥市 / 庐阳区")).toBeVisible();
  await page.getByText("AI", { exact: true }).click();
  await page.getByText("Python", { exact: true }).click();
  await page.getByRole("button", { name: "保存偏好" }).click();
  await expect(page.getByRole("status")).toHaveText("偏好已保存。");
  expect(timezone).toBe("Asia/Shanghai");
  expect(weatherLocation).toBe("安徽省 / 合肥市 / 庐阳区");
  expect(newsTopics).toEqual(["AI", "Python"]);
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

test("loads a previous conversation from its stable URL", async ({ page }) => {
  const conversationId = "11111111-1111-4111-8111-111111111111";
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({ status: 403, json: { detail: "Not authenticated." } });
  });
  await page.route("**/api/v1/chat/conversations/", async (route) => {
    await route.fulfill({
      json: [{
        id: conversationId,
        title: "今天的安排",
        created_at: "2026-07-17T08:00:00Z",
        updated_at: new Date().toISOString(),
      }],
    });
  });
  await page.route("**/api/v1/action-proposals/", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/api/v1/chat/conversations/${conversationId}/`, async (route) => {
    await route.fulfill({
      json: {
        id: conversationId,
        title: "今天的安排",
        created_at: "2026-07-17T08:00:00Z",
        updated_at: new Date().toISOString(),
        runs: [{
          id: "22222222-2222-4222-8222-222222222222",
          conversation_id: conversationId,
          operation_id: "33333333-3333-4333-8333-333333333333",
          request_id: "history-request",
          status: "completed",
          input_message: "今天有什么安排？",
          final_response: "你今天下午三点有项目会议。",
          error: "",
          started_at: "2026-07-17T08:00:00Z",
          completed_at: "2026-07-17T08:00:01Z",
          created_at: "2026-07-17T08:00:00Z",
        }],
      },
    });
  });

  await page.goto(`/chat/${conversationId}`);

  await expect(page).toHaveURL(new RegExp(`/chat/${conversationId}$`));
  await expect(page.getByRole("heading", { name: "今天的安排" })).toBeVisible();
  await expect(page.getByText("今天有什么安排？")).toBeVisible();
  await expect(page.getByText("你今天下午三点有项目会议。")).toBeVisible();
  await expect(page.getByRole("button", { name: "今天的安排" })).toHaveAttribute("aria-current", "page");
});

test("creates a new chat, updates the URL, and streams the reply", async ({ page }) => {
  const conversationId = "11111111-1111-4111-8111-111111111111";
  const runId = "22222222-2222-4222-8222-222222222222";
  let conversationCreated = false;
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({ status: 403, json: { detail: "Not authenticated." } });
  });
  await page.route("**/api/v1/chat/conversations/", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: conversationCreated ? [{
          id: conversationId,
          title: "今天有什么安排？",
          created_at: "2026-07-17T08:00:00Z",
          updated_at: new Date().toISOString(),
        }] : [],
      });
      return;
    }
    conversationCreated = true;
    await route.fulfill({
      status: 201,
      json: {
        id: conversationId,
        title: "",
        created_at: "2026-07-17T08:00:00Z",
        updated_at: "2026-07-17T08:00:00Z",
      },
    });
  });
  await page.route("**/api/v1/action-proposals/", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/api/v1/chat/conversations/${conversationId}/`, async (route) => {
    await route.fulfill({
      json: {
        id: conversationId,
        title: "今天有什么安排？",
        created_at: "2026-07-17T08:00:00Z",
        updated_at: new Date().toISOString(),
        runs: [{
          id: runId,
          conversation_id: conversationId,
          operation_id: "33333333-3333-4333-8333-333333333333",
          request_id: "e2e-request",
          status: "running",
          input_message: "今天有什么安排？",
          final_response: "",
          error: "",
          started_at: "2026-07-17T08:00:00Z",
          completed_at: null,
          created_at: "2026-07-17T08:00:00Z",
        }],
      },
    });
  });
  await page.route("**/api/v1/chat/messages/", async (route) => {
    await route.fulfill({
      status: 202,
      json: {
        id: runId,
        conversation_id: conversationId,
        operation_id: "33333333-3333-4333-8333-333333333333",
        request_id: "e2e-request",
        status: "pending",
        input_message: "今天有什么安排？",
        final_response: "",
        error: "",
        started_at: null,
        completed_at: null,
        created_at: "2026-07-17T08:00:00Z",
      },
    });
  });
  await page.route(`**/api/v1/chat/runs/${runId}/events/**`, async (route) => {
    await route.fulfill({
      contentType: "text/event-stream",
      body: [
        'id: 1\nevent: tool.started\ndata: {"tool_call_id":"tool-1","tool_name":"list_events"}\n\n',
        'id: 2\nevent: tool.completed\ndata: {"tool_call_id":"tool-1","tool_name":"list_events"}\n\n',
        'id: 3\nevent: message.completed\ndata: {"content":"你今天没有安排。"}\n\n',
      ].join(""),
    });
  });

  await page.goto("/chat");
  await expect(page.getByRole("heading", { name: "今天需要我帮你安排什么？" })).toBeVisible();
  await page.getByRole("textbox", { name: "消息", exact: true }).fill("今天有什么安排？");
  await page.getByRole("button", { name: "发送消息" }).click();

  await expect(page).toHaveURL(new RegExp(`/chat/${conversationId}$`));
  const executionDetails = page.getByRole("region", { name: "执行详情" }).locator("summary");
  await expect(page.getByText("list_events")).toBeHidden();
  await executionDetails.click();
  await expect(page.getByText("list_events")).toBeVisible();
  await expect(page.getByText("已完成")).toBeVisible();
  await expect(page.getByText("你今天没有安排。")).toBeVisible();

  await page.getByRole("button", { name: "新建聊天" }).first().click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole("heading", { name: "今天需要我帮你安排什么？" })).toBeVisible();
});

test("reviews and approves a high-risk action", async ({ page }) => {
  let proposalStatus = "awaiting_approval";
  const proposal = {
    id: "44444444-4444-4444-8444-444444444444",
    conversation_id: "11111111-1111-4111-8111-111111111111",
    agent_run_id: "22222222-2222-4222-8222-222222222222",
    original_request: "明天下午三点创建项目评审日程",
    explanation: "创建正式日程会占用你的日历时间，需要确认后执行。",
    action_type: "create_event",
    action_payload: {
      title: "项目评审",
      start_at: "2026-07-20T07:00:00Z",
      end_at: "2026-07-20T08:00:00Z",
      timezone: "Asia/Shanghai",
    },
    original_payload: {},
    display_context: {
      allowed_decisions: ["approve", "edit", "reject"],
      action_title: "创建日程",
      action_summary: "将创建日程「项目评审」。",
      object_name: "项目评审",
      impact_scope: "创建一个正式日程",
      proposed_start_at: "2026-07-20T07:00:00Z",
      proposed_end_at: "2026-07-20T08:00:00Z",
      conflict_check: "completed",
      conflicts: [],
    },
    risk_level: "high",
    status: "awaiting_approval",
    requires_approval: true,
    version: 1,
    expires_at: "2026-07-20T08:00:00Z",
    decided_at: null,
    approved_at: null,
    resumed_at: null,
    executed_at: null,
    decision_reason: "",
    execution_result: null,
    error: "",
    created_at: "2026-07-19T08:00:00Z",
    updated_at: "2026-07-19T08:00:00Z",
  };
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({ status: 403, json: { detail: "Not authenticated." } });
  });
  await page.route("**/api/v1/action-proposals/?status=awaiting_approval", async (route) => {
    await route.fulfill({
      json: proposalStatus === "awaiting_approval" ? [{ ...proposal, status: proposalStatus }] : [],
    });
  });
  await page.route(`**/api/v1/action-proposals/${proposal.id}/approve/`, async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({ expected_version: 1 });
    proposalStatus = "approved";
    await route.fulfill({
      status: 202,
      json: {
        proposal: { ...proposal, status: "approved", version: 2 },
        resume_queued: true,
      },
    });
  });

  await page.goto("/approvals");
  await expect(page.getByRole("heading", { name: "操作审批" })).toBeVisible();
  await expect(page.getByText("以下时间均按 Asia/Shanghai 显示。", { exact: true })).toBeVisible();
  await expect(page.getByText(/Agent 提出的高风险操作/)).toHaveCount(0);
  await expect(page.getByText("未发现日程冲突。")).toBeVisible();
  await page.getByRole("button", { name: "确认并应用", exact: true }).click();
  await expect(page.getByRole("button", { name: "确认并应用", exact: true })).toHaveCount(0);
});

test("shows the conflict context before a user decides on approval", async ({ page }) => {
  const proposal = {
    id: "abababab-abab-4bab-8bab-abababababab",
    conversation_id: "11111111-1111-4111-8111-111111111111",
    agent_run_id: "22222222-2222-4222-8222-222222222222",
    original_request: "把项目评审安排在明天下午三点。",
    explanation: "创建正式日程会占用你的日历时间，需要确认后执行。",
    action_type: "create_event",
    action_payload: {
      title: "项目评审",
      start_at: "2026-10-01T07:00:00Z",
      end_at: "2026-10-01T08:00:00Z",
      timezone: "Asia/Shanghai",
    },
    original_payload: {},
    display_context: {
      allowed_decisions: ["approve", "edit", "reject"],
      action_title: "创建日程",
      action_summary: "将创建日程「项目评审」。",
      object_name: "项目评审",
      impact_scope: "创建一个正式日程",
      proposed_start_at: "2026-10-01T07:00:00Z",
      proposed_end_at: "2026-10-01T08:00:00Z",
      conflict_check: "completed",
      conflicts: [{
        id: "cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd",
        title: "客户评审",
        start_at: "2026-10-01T07:30:00Z",
        end_at: "2026-10-01T08:30:00Z",
        overlap_start_at: "2026-10-01T07:30:00Z",
        overlap_end_at: "2026-10-01T08:00:00Z",
      }],
    },
    risk_level: "high",
    status: "awaiting_approval",
    requires_approval: true,
    version: 1,
    expires_at: "2026-10-01T08:00:00Z",
    decided_at: null,
    approved_at: null,
    resumed_at: null,
    executed_at: null,
    decision_reason: "",
    execution_result: null,
    error: "",
    created_at: "2026-09-30T08:00:00Z",
    updated_at: "2026-09-30T08:00:00Z",
  };
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({ json: { timezone: "Asia/Shanghai", locale: "zh-CN" } });
  });
  await page.route("**/api/v1/action-proposals/?status=awaiting_approval", async (route) => {
    await route.fulfill({ json: [proposal] });
  });

  await page.goto("/approvals");
  await expect(page.getByRole("heading", { name: "操作审批" })).toBeVisible();
  await expect(page.getByText("发现 1 个时间冲突。请核对重叠时段，调整到无冲突时间，或拒绝这项操作。")).toBeVisible();
  await expect(page.getByText("客户评审", { exact: true })).toBeVisible();
  await expect(page.getByText("已占用：2026/10/01 15:30 – 16:30")).toBeVisible();
  await expect(page.getByText("与你的提议重叠：2026/10/01 15:30 – 16:00")).toBeVisible();
  await expect(page.getByRole("group", { name: "冲突日程详情" })).toBeVisible();
  await expect(page.getByText("在你确认前，这项操作不会执行。")).toBeVisible();
  await expect(page.getByText("重复操作")).toHaveCount(0);
  await expect(page.getByText("提出时间")).not.toBeVisible();
  await expect(page.getByRole("button", { name: "确认并应用", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "先调整时间", exact: true })).toBeVisible();
  await page.screenshot({
    path: "../docs/experiments/agent-ux-evaluation/screenshots/approval-conflict-after.png",
    fullPage: true,
  });
  await page.getByText("发现 1 个时间冲突。请核对重叠时段，调整到无冲突时间，或拒绝这项操作。").evaluate((element) => {
    element.scrollIntoView({ block: "center" });
  });
  await page.screenshot({
    path: "../docs/experiments/agent-ux-evaluation/screenshots/approval-conflict-after-focus.png",
  });
  await page.setViewportSize({ width: 320, height: 800 });
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 320);
  await page.screenshot({
    path: "../docs/experiments/agent-ux-evaluation/screenshots/approval-conflict-mobile-single-320.png",
  });
  await page.setViewportSize({ width: 390, height: 844 });

  Object.assign(proposal.display_context.conflicts[0], {
    overlap_start_at: null,
    overlap_end_at: null,
  });
  await page.reload();
  await expect(page.getByText("客户评审", { exact: true })).toBeVisible();
  await expect(page.getByText(/与你的提议重叠/)).toHaveCount(0);
  await page.getByText("发现 1 个时间冲突。请核对重叠时段，调整到无冲突时间，或拒绝这项操作。")
    .evaluate((element) => element.scrollIntoView({ block: "center" }));
  await page.screenshot({
    path: "../docs/experiments/agent-ux-evaluation/screenshots/approval-conflict-context-only-focus.png",
  });
  await page.screenshot({
    path: "../docs/experiments/agent-ux-evaluation/screenshots/approval-conflict-context-only-final.png",
  });
  await page.locator("summary").filter({ hasText: "查看操作详情" }).click();
  await expect(page.getByText("提出时间")).toBeVisible();
  await expect(page.getByText("重复操作")).toHaveCount(0);
});

test("shows the old and proposed time for a conflicting event move", async ({ page }) => {
  const proposal = {
    id: "cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd",
    conversation_id: "11111111-1111-4111-8111-111111111111",
    agent_run_id: "22222222-2222-4222-8222-222222222222",
    original_request: "把周四的日程挪到下午，先告诉我是否冲突。",
    explanation: "update_event",
    action_type: "update_event",
    action_payload: {
      event_id: "abababab-abab-4bab-8bab-abababababab",
      expected_version: 2,
      start_at: "2026-10-01T07:00:00Z",
      end_at: "2026-10-01T08:00:00Z",
      timezone: "Asia/Shanghai",
    },
    original_payload: {},
    display_context: {
      allowed_decisions: ["approve", "edit", "reject"],
      action_title: "修改日程",
      action_summary: "将把日程「周四论文讨论」调整到新时间。",
      conflict_action: "调整",
      conflict_check: "completed",
      review_items: [{
        title: "周四论文讨论",
        detail: "查看原安排与调整后的时间",
        time_label: "原安排",
        proposed_time_label: "调整为",
        start_at: "2026-10-01T02:00:00Z",
        end_at: "2026-10-01T03:00:00Z",
        proposed_start_at: "2026-10-01T07:00:00Z",
        proposed_end_at: "2026-10-01T08:00:00Z",
      }],
      review_complete: true,
      conflicts: [{
        title: "客户评审",
        start_at: "2026-10-01T07:30:00Z",
        end_at: "2026-10-01T08:30:00Z",
        overlap_start_at: "2026-10-01T07:30:00Z",
        overlap_end_at: "2026-10-01T08:00:00Z",
      }],
    },
    risk_level: "high",
    status: "awaiting_approval",
    requires_approval: true,
    version: 1,
    expires_at: "2026-10-01T08:00:00Z",
    decided_at: null,
    approved_at: null,
    resumed_at: null,
    executed_at: null,
    decision_reason: "",
    execution_result: null,
    error: "",
    created_at: "2026-09-30T08:00:00Z",
    updated_at: "2026-09-30T08:00:00Z",
  };
  await page.setViewportSize({ width: 320, height: 800 });
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({ json: { timezone: "Asia/Shanghai", locale: "zh-CN" } });
  });
  await page.route("**/api/v1/action-proposals/?status=awaiting_approval", async (route) => {
    await route.fulfill({ json: [proposal] });
  });

  await page.goto("/approvals");
  await expect(page.getByRole("heading", { name: "修改日程" })).toBeVisible();
  await expect(page.getByText("2026/10/01 10:00 – 11:00")).toBeVisible();
  await expect(page.getByText("2026/10/01 15:00 – 16:00")).toBeVisible();
  await expect(page.getByText("发现 1 个时间冲突。请核对重叠时段，调整到无冲突时间，或拒绝这项操作。"))
    .toBeVisible();
  await expect(page.getByText("与你的提议重叠：2026/10/01 15:30 – 16:00")).toBeVisible();
  await expect(page.getByRole("button", { name: "确认并应用", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "先调整时间", exact: true })).toBeVisible();
  const conflictSummary = page.getByText("发现 1 个时间冲突。请核对重叠时段，调整到无冲突时间，或拒绝这项操作。");
  await conflictSummary.evaluate((element) => element.scrollIntoView({ block: "center" }));
  const conflictBounds = await page.getByText("与你的提议重叠：2026/10/01 15:30 – 16:00").boundingBox();
  const navigationBounds = await page.locator('nav[aria-label="移动端主导航"]').boundingBox();
  expect(conflictBounds).not.toBeNull();
  expect(navigationBounds).not.toBeNull();
  expect(conflictBounds!.y + conflictBounds!.height).toBeLessThanOrEqual(navigationBounds!.y);
  await page.screenshot({
    path: "../docs/experiments/agent-ux-evaluation/screenshots/approval-reschedule-holdout-mobile-320.png",
  });
  const adjustmentButton = page.getByRole("button", { name: "先调整时间", exact: true });
  await adjustmentButton.evaluate((element) => element.scrollIntoView({ block: "center" }));
  const actionViewOverlapBounds = await page.getByText("与你的提议重叠：2026/10/01 15:30 – 16:00").boundingBox();
  const actionViewButtonBounds = await adjustmentButton.boundingBox();
  const actionViewNavigationBounds = await page.locator('nav[aria-label="移动端主导航"]').boundingBox();
  expect(actionViewOverlapBounds).not.toBeNull();
  expect(actionViewButtonBounds).not.toBeNull();
  expect(actionViewNavigationBounds).not.toBeNull();
  expect(actionViewOverlapBounds!.y + actionViewOverlapBounds!.height)
    .toBeLessThanOrEqual(actionViewNavigationBounds!.y);
  expect(actionViewButtonBounds!.y + actionViewButtonBounds!.height)
    .toBeLessThanOrEqual(actionViewNavigationBounds!.y);
  await page.screenshot({
    path: "../docs/experiments/agent-ux-evaluation/screenshots/approval-reschedule-action-mobile-320.png",
  });
  Object.assign(proposal.display_context.conflicts[0], {
    overlap_start_at: null,
    overlap_end_at: null,
  });
  await page.reload();
  const contextOnlySummary = page.getByText("发现 1 个时间冲突。请核对重叠时段，调整到无冲突时间，或拒绝这项操作。");
  await contextOnlySummary.evaluate((element) => element.scrollIntoView({ block: "center" }));
  await expect(page.getByText(/与你的提议重叠/)).toHaveCount(0);
  await page.screenshot({
    path: "../docs/experiments/agent-ux-evaluation/screenshots/approval-reschedule-context-only-mobile-320.png",
  });
  await page.getByRole("button", { name: "先调整时间", exact: true })
    .evaluate((element) => element.scrollIntoView({ block: "center" }));
  await page.screenshot({
    path: "../docs/experiments/agent-ux-evaluation/screenshots/approval-reschedule-context-only-action-mobile-320.png",
  });
});

test("opens additional approval conflicts with the keyboard", async ({ page }) => {
  const proposal = {
    id: "abababab-abab-4bab-8bab-abababababab",
    conversation_id: "11111111-1111-4111-8111-111111111111",
    agent_run_id: "22222222-2222-4222-8222-222222222222",
    original_request: "把项目评审安排在明天下午三点。",
    explanation: "创建正式日程会占用你的日历时间，需要确认后执行。",
    action_type: "create_event",
    action_payload: {
      title: "项目评审",
      start_at: "2026-10-01T07:00:00Z",
      end_at: "2026-10-01T08:00:00Z",
      timezone: "Asia/Shanghai",
    },
    original_payload: {},
    display_context: {
      allowed_decisions: ["approve", "edit", "reject"],
      conflict_check: "completed",
      conflicts: Array.from({ length: 4 }, (_, index) => ({
        id: `cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcd0${index}`,
        title: ["客户评审", "团队同步", "供应商沟通", "项目例会"][index] ?? "已有日程",
        start_at: "2026-10-01T07:30:00Z",
        end_at: "2026-10-01T08:30:00Z",
        overlap_start_at: "2026-10-01T07:30:00Z",
        overlap_end_at: "2026-10-01T08:00:00Z",
      })),
    },
    risk_level: "high",
    status: "awaiting_approval",
    requires_approval: true,
    version: 1,
    expires_at: "2026-10-01T08:00:00Z",
    decided_at: null,
    approved_at: null,
    resumed_at: null,
    executed_at: null,
    decision_reason: "",
    execution_result: null,
    error: "",
    created_at: "2026-09-30T08:00:00Z",
    updated_at: "2026-09-30T08:00:00Z",
  };
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({ json: { timezone: "Asia/Shanghai", locale: "zh-CN" } });
  });
  await page.route("**/api/v1/action-proposals/?status=awaiting_approval", async (route) => {
    await route.fulfill({ json: [proposal] });
  });

  for (const viewport of [{ width: 320, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/approvals");
    await expect(page.getByText("以下时间均按 Asia/Shanghai 显示。", { exact: true })).toBeVisible();
    await expect(page.getByText(/Agent 提出的高风险操作/)).toHaveCount(0);
    const disclosure = page.locator("summary").filter({ hasText: "查看其余 1 个冲突" });
    await expect(disclosure).toBeVisible();
    const disclosureBounds = await disclosure.boundingBox();
    expect(disclosureBounds?.height).toBeGreaterThanOrEqual(44);
    expect(disclosureBounds?.width).toBeGreaterThanOrEqual(44);
    const navigation = page.locator('nav[aria-label="移动端主导航"]');
    for (const label of ["全部", "等待审批", "已执行", "已拒绝", "已过期", "执行失败"]) {
      await page.keyboard.press("Tab");
      const filterButton = page.getByRole("button", { name: label, exact: true });
      await expect(filterButton).toBeFocused();
      await expect(filterButton).toHaveAttribute("aria-pressed", String(label === "等待审批"));
      const filterBounds = await filterButton.boundingBox();
      expect(filterBounds?.height).toBeGreaterThanOrEqual(44);
      expect(filterBounds?.width).toBeGreaterThanOrEqual(44);
      const filterOwnsHitTarget = await filterButton.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const hitTarget = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
        return hitTarget !== null && element.contains(hitTarget);
      });
      expect(filterOwnsHitTarget).toBe(true);
    }
    await disclosure.evaluate((element) => element.scrollIntoView({ block: "center" }));
    await page.keyboard.press("Tab");
    await expect(disclosure).toBeFocused();
    await expect(disclosure).not.toHaveCSS("outline-style", "none");
    const disclosureFocusBounds = await disclosure.boundingBox();
    const disclosureNavigationBounds = await navigation.boundingBox();
    expect(disclosureFocusBounds).not.toBeNull();
    expect(disclosureNavigationBounds).not.toBeNull();
    expect(disclosureFocusBounds!.width).toBeGreaterThanOrEqual(44);
    expect(disclosureFocusBounds!.y + disclosureFocusBounds!.height).toBeLessThanOrEqual(disclosureNavigationBounds!.y);
    const disclosureOwnsHitTarget = await disclosure.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const hitTarget = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return hitTarget !== null && element.contains(hitTarget);
    });
    expect(disclosureOwnsHitTarget).toBe(true);
    await page.keyboard.press("Enter");
    await expect(page.getByText("客户评审", { exact: true })).toBeVisible();
    await expect(page.getByText("项目例会", { exact: true })).toBeVisible();
    await expect(page.getByRole("group", { name: "冲突日程详情" })).toBeVisible();
    if (viewport.width === 320) {
      await page.screenshot({
        path: "../docs/experiments/agent-ux-evaluation/screenshots/approval-conflict-mobile-320.png",
      });
    }
    await expect(page.locator("body")).toHaveJSProperty("scrollWidth", viewport.width);

    const operationDetails = page.locator("summary").filter({ hasText: "查看操作详情" });
    await operationDetails.evaluate((element) => element.scrollIntoView({ block: "center" }));
    const operationDetailsBounds = await operationDetails.boundingBox();
    expect(operationDetailsBounds?.height).toBeGreaterThanOrEqual(44);
    expect(operationDetailsBounds?.width).toBeGreaterThanOrEqual(44);
    await page.keyboard.press("Tab");
    await expect(operationDetails).toBeFocused();
    const operationDetailsFocusBounds = await operationDetails.boundingBox();
    const operationDetailsNavigationBounds = await navigation.boundingBox();
    expect(operationDetailsFocusBounds).not.toBeNull();
    expect(operationDetailsNavigationBounds).not.toBeNull();
    expect(operationDetailsFocusBounds!.width).toBeGreaterThanOrEqual(44);
    expect(operationDetailsFocusBounds!.y + operationDetailsFocusBounds!.height).toBeLessThanOrEqual(operationDetailsNavigationBounds!.y);
    const operationDetailsOwnsHitTarget = await operationDetails.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const hitTarget = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return hitTarget !== null && element.contains(hitTarget);
    });
    expect(operationDetailsOwnsHitTarget).toBe(true);

    const decisionControls = [
      page.getByRole("button", { name: "先调整时间", exact: true }),
      page.getByRole("button", { name: "拒绝", exact: true }),
    ];
    for (const control of decisionControls) {
      await page.keyboard.press("Tab");
      await expect(control).toBeFocused();
      const controlBounds = await control.boundingBox();
      const navigationBounds = await navigation.boundingBox();
      expect(controlBounds?.height).toBeGreaterThanOrEqual(44);
      expect(controlBounds).not.toBeNull();
      expect(navigationBounds).not.toBeNull();
      expect(controlBounds!.width).toBeGreaterThanOrEqual(44);
      expect(controlBounds!.y + controlBounds!.height).toBeLessThanOrEqual(navigationBounds!.y);
      if (control === decisionControls[0]) {
        await expect(control).toHaveCSS("outline-style", "solid");
        await expect(control).toHaveCSS("outline-width", "3px");
      }
      const controlOwnsHitTarget = await control.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const hitTarget = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
        return hitTarget !== null && element.contains(hitTarget);
      });
      expect(controlOwnsHitTarget).toBe(true);
    }
    const rejectionReason = page.getByRole("textbox", { name: "拒绝原因" });
    await page.keyboard.press("Tab");
    await expect(rejectionReason).toBeFocused();
    const rejectionReasonBounds = await rejectionReason.boundingBox();
    expect(rejectionReasonBounds?.height).toBeGreaterThanOrEqual(44);
    expect(rejectionReasonBounds?.width).toBeGreaterThanOrEqual(44);
    await page.evaluate(() => {
      const visualViewport = window.visualViewport;
      if (!visualViewport) return;
      Object.defineProperty(visualViewport, "height", { configurable: true, value: 500 });
      visualViewport.dispatchEvent(new Event("resize"));
    });
    await expect(navigation).toHaveAttribute("aria-hidden", "true");
    await expect(navigation).toHaveAttribute("inert", "");
    await page.evaluate(() => {
      const visualViewport = window.visualViewport;
      if (!visualViewport) return;
      Object.defineProperty(visualViewport, "height", { configurable: true, value: window.innerHeight });
      visualViewport.dispatchEvent(new Event("resize"));
    });
    await expect(navigation).toHaveAttribute("aria-hidden", "false");
    await expect(navigation).not.toHaveAttribute("inert", "");
    await expect(rejectionReason).toBeFocused();

    const editButton = page.getByRole("button", { name: "先调整时间", exact: true });
    await editButton.focus();
    await page.keyboard.press("Enter");
    const reopenedDetails = page.locator("details").filter({ hasText: "查看操作详情" });
    await expect(reopenedDetails).toHaveAttribute("open", "");
    await expect(page.getByLabel("日程标题").first()).toBeFocused();
    await page.getByRole("button", { name: "取消编辑" }).click();
    await expect(editButton).toBeFocused();

    await rejectionReason.focus();
    await page.evaluate(() => {
      const visualViewport = window.visualViewport;
      if (!visualViewport) return;
      Object.defineProperty(visualViewport, "height", { configurable: true, value: 500 });
      visualViewport.dispatchEvent(new Event("resize"));
    });
    await expect(navigation).toHaveAttribute("aria-hidden", "true");
    await page.keyboard.press("Tab");
    const focusInsideHiddenNavigation = await navigation.evaluate((element) => element.contains(document.activeElement));
    expect(focusInsideHiddenNavigation).toBe(false);
  }

  await page.addInitScript(() => {
    Object.defineProperty(window, "visualViewport", { configurable: true, value: null });
  });
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/approvals");
  const navigation = page.locator('nav[aria-label="移动端主导航"]');
  const rejectionReason = page.getByRole("textbox", { name: "拒绝原因" });
  await rejectionReason.focus();
  await expect(navigation).toHaveAttribute("aria-hidden", "true");
  await expect(navigation).toHaveAttribute("inert", "");
  await rejectionReason.evaluate((element) => element.blur());
  await expect(navigation).toHaveAttribute("aria-hidden", "false");
  await expect(navigation).not.toHaveAttribute("inert", "");
});

test("continues the chat stream after approving an interrupted run", async ({ page }) => {
  const conversationId = "55555555-5555-4555-8555-555555555555";
  const runId = "66666666-6666-4666-8666-666666666666";
  const proposalId = "77777777-7777-4777-8777-777777777777";
  const conversation = {
    id: conversationId,
    title: "创建项目评审日程",
    created_at: "2026-07-19T08:00:00Z",
    updated_at: "2026-07-19T08:00:00Z",
  };
  const run = {
    id: runId,
    conversation_id: conversationId,
    operation_id: "88888888-8888-4888-8888-888888888888",
    request_id: "approval-resume-request",
    status: "running",
    input_message: "明天下午三点创建项目评审日程",
    final_response: "",
    error: "",
    started_at: "2026-07-19T08:00:00Z",
    completed_at: null,
    created_at: "2026-07-19T08:00:00Z",
  };
  const proposal = {
    id: proposalId,
    conversation_id: conversationId,
    agent_run_id: runId,
    original_request: run.input_message,
    explanation: "创建正式日程会占用你的日历时间，需要确认后执行。",
    action_type: "create_event",
    action_payload: {
      title: "项目评审",
      start_at: "2026-07-20T07:00:00Z",
      end_at: "2026-07-20T08:00:00Z",
      timezone: "Asia/Shanghai",
    },
    original_payload: {},
    display_context: {
      allowed_decisions: ["approve", "edit", "reject"],
      object_name: "项目评审",
      impact_scope: "创建一个正式日程",
    },
    risk_level: "high",
    status: "awaiting_approval",
    requires_approval: true,
    version: 1,
    expires_at: "2026-07-20T08:00:00Z",
    decided_at: null,
    approved_at: null,
    resumed_at: null,
    executed_at: null,
    decision_reason: "",
    execution_result: null,
    error: "",
    created_at: "2026-07-19T08:00:00Z",
    updated_at: "2026-07-19T08:00:00Z",
  };
  const cursors: string[] = [];

  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({ status: 403, json: { detail: "Not authenticated." } });
  });
  await page.route("**/api/v1/chat/conversations/", async (route) => {
    await route.fulfill({ json: [conversation] });
  });
  await page.route(`**/api/v1/chat/conversations/${conversationId}/`, async (route) => {
    await route.fulfill({ json: { ...conversation, runs: [run] } });
  });
  await page.route("**/api/v1/action-proposals/", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/api/v1/action-proposals/${proposalId}/`, async (route) => {
    await route.fulfill({ json: proposal });
  });
  await page.route(`**/api/v1/action-proposals/${proposalId}/approve/`, async (route) => {
    await route.fulfill({
      status: 202,
      json: {
        proposal: { ...proposal, status: "approved", version: 2 },
        resume_queued: true,
      },
    });
  });
  await page.route(`**/api/v1/chat/runs/${runId}/events/**`, async (route) => {
    const cursor = new URL(route.request().url()).searchParams.get("cursor") ?? "";
    cursors.push(cursor);
    const body = cursor === "3"
      ? [
          `id: 4\nevent: agent.resumed\ndata: {"run_id":"${runId}"}\n\n`,
          'id: 5\nevent: tool.completed\ndata: {"tool_call_id":"create-1","tool_name":"create_event"}\n\n',
          'id: 6\nevent: message.delta\ndata: {"content":"日程已创建。"}\n\n',
          'id: 7\nevent: message.completed\ndata: {"content":"日程已创建。"}\n\n',
        ].join("")
      : [
          `id: 1\nevent: agent.started\ndata: {"run_id":"${runId}"}\n\n`,
          'id: 2\nevent: message.delta\ndata: {"content":"没有冲突。"}\n\n',
          `id: 3\nevent: approval.required\ndata: {"proposal_id":"${proposalId}"}\n\n`,
        ].join("");
    await route.fulfill({ contentType: "text/event-stream", body });
  });

  await page.goto(`/chat/${conversationId}`);
  await page.getByRole("button", { name: "确认并应用", exact: true }).click();

  await expect(page.getByText("日程已创建。")).toBeVisible();
  expect(cursors).toEqual(["0", "3"]);
});

test("launches a manual briefing into its own conversation", async ({ page }) => {
  const conversationId = "99999999-9999-4999-8999-999999999999";
  const runId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const conversation = {
    id: conversationId,
    title: "E2E Manual Briefing",
    kind: "manual_briefing",
    created_at: "2026-07-19T00:00:00Z",
    updated_at: "2026-07-19T00:00:01Z",
  };
  const run = {
    id: runId,
    conversation_id: conversationId,
    operation_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    request_id: "briefing-e2e-request",
    trigger_type: "manual_briefing",
    trigger_payload: { target_date: "2026-07-19" },
    synthetic_input: true,
    status: "completed",
    input_message: "Generate the daily briefing for 2026-07-19.",
    final_response: "# E2E Briefing\n\nNo events or tasks today.",
    error: "",
    started_at: "2026-07-19T00:00:00Z",
    completed_at: "2026-07-19T00:00:01Z",
    created_at: "2026-07-19T00:00:00Z",
  };

  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({ status: 403, json: { detail: "Not authenticated." } });
  });
  await page.route("**/api/v1/briefings/definitions/", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/v1/briefings/runs/", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 202, json: { conversation, agent_run: { ...run, status: "pending", final_response: "", completed_at: null } } });
      return;
    }
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/v1/chat/conversations/", async (route) => {
    await route.fulfill({ json: [conversation] });
  });
  await page.route(`**/api/v1/chat/conversations/${conversationId}/`, async (route) => {
    await route.fulfill({ json: { ...conversation, runs: [run] } });
  });
  await page.route("**/api/v1/action-proposals/", async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/briefings");
  await expect(page.getByText("Briefing Workflow")).toBeVisible();
  await page.locator("section button").first().click();

  await expect(page).toHaveURL(new RegExp(`/chat/${conversationId}$`));
  await expect(page.getByRole("heading", { name: "E2E Manual Briefing" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "E2E Briefing" })).toBeVisible();
});

test("opens notification settings, enables email, and shows delivery status", async ({ page }) => {
  let emailEnabled = false;
  await page.route("**/api/v1/preferences/me/", async (route) => {
    await route.fulfill({
      json: {
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
        weather_location_data: {},
        weather_forecast_days: 3,
        require_event_creation_approval: false,
        require_event_cancellation_approval: false,
        news_topics: [],
        briefing_time: "08:00:00",
        planning_rules: {},
        updated_at: "2026-07-21T00:00:00Z",
      },
    });
  });
  await page.route("**/api/v1/notification-preferences/me/", async (route) => {
    if (route.request().method() === "PATCH") {
      emailEnabled = Boolean(route.request().postDataJSON().reminder_email_enabled);
    }
    await route.fulfill({
      json: {
        email: "e2e@example.test",
        reminder_console_enabled: true,
        reminder_email_enabled: emailEnabled,
        reminder_web_push_enabled: false,
        briefing_console_enabled: true,
        briefing_email_enabled: false,
        briefing_web_push_enabled: false,
        updated_at: "2026-07-21T00:00:00Z",
      },
    });
  });
  await page.route("**/api/v1/notification-deliveries/", async (route) => {
    await route.fulfill({ json: [{
      id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      source_type: "reminder",
      source_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
      channel_type: "email",
      status: "sent",
      subject: "E2E reminder",
      scheduled_at: "2026-07-21T00:00:00Z",
      queued_at: "2026-07-21T00:00:00Z",
      sending_at: "2026-07-21T00:00:01Z",
      sent_at: "2026-07-21T00:00:02Z",
      failed_at: null,
      attempt_count: 1,
      next_retry_at: null,
      provider_message_id: "e2e-message",
      failure_code: "",
      failure_reason: "",
      created_at: "2026-07-21T00:00:00Z",
      updated_at: "2026-07-21T00:00:02Z",
    }] });
  });
  await page.route("**/api/v1/web-push/config/", async (route) => {
    await route.fulfill({ json: { configured: false, public_key: "" } });
  });
  await page.route("**/api/v1/web-push/subscriptions/", async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/settings/notifications");
  await expect(page.getByRole("heading", { name: "通知设置" })).toBeVisible();
  await page.getByLabel("提醒邮件").click();
  await expect(page.getByLabel("提醒邮件")).toBeChecked();
  expect(emailEnabled).toBe(true);
  await expect(page.getByText("E2E reminder")).toBeVisible();
  await expect(page.getByText("sent", { exact: true })).toBeVisible();
});
