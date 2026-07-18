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
