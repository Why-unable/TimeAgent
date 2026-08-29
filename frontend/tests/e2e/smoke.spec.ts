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
  await page.getByRole("checkbox", { name: /准备规划演示/ }).click();
  await page.getByRole("button", { name: "生成草案" }).click();
  await expect(page.getByText("已安排")).toBeVisible();
  await page.getByRole("button", { name: "确认应用" }).click();
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
  await expect(page.getByText("未发现日程冲突。")).toBeVisible();
  await page.getByRole("button", { name: "批准", exact: true }).click();
  await expect(page.getByRole("button", { name: "批准", exact: true })).toHaveCount(0);
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
  await page.getByRole("button", { name: "批准", exact: true }).click();

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
