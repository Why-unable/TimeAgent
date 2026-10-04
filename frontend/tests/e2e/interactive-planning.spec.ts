import { expect, test, type Page, type TestInfo } from "@playwright/test";

const planId = "33333333-3333-4333-8333-333333333333";
const paperId = "11111111-1111-4111-8111-111111111111";
const redisId = "22222222-2222-4222-8222-222222222222";
const completionTask = {
  id: paperId,
  project: "论文",
  parent_task: null,
  title: "论文",
  description: "",
  status: "pending",
  priority: "medium",
  due_at: "2026-10-02T12:00:00Z",
  estimated_minutes: 60,
  planned_start_at: "2026-10-02T09:00:00Z",
  planned_end_at: "2026-10-02T10:00:00Z",
  actual_started_at: null,
  completed_at: null,
  source: "local",
  tags: [],
  version: 1,
  created_at: "2026-10-02T00:00:00Z",
  updated_at: "2026-10-02T00:00:00Z",
};

const tasks = [
  {
    id: paperId,
    project: "论文",
    parent_task: null,
    title: "论文",
    description: "",
    status: "pending",
    priority: "medium",
    due_at: null,
    estimated_minutes: 60,
    planned_start_at: null,
    planned_end_at: null,
    actual_started_at: null,
    completed_at: null,
    source: "local",
    tags: [],
    version: 1,
    created_at: "2026-10-02T00:00:00Z",
    updated_at: "2026-10-02T00:00:00Z",
  },
  {
    id: redisId,
    project: "工程",
    parent_task: null,
    title: "Redis",
    description: "",
    status: "pending",
    priority: "low",
    due_at: null,
    estimated_minutes: 60,
    planned_start_at: null,
    planned_end_at: null,
    actual_started_at: null,
    completed_at: null,
    source: "local",
    tags: [],
    version: 1,
    created_at: "2026-10-02T00:00:00Z",
    updated_at: "2026-10-02T00:00:00Z",
  },
];

function draft(version = 1, order: string[] = [paperId, redisId]) {
  return {
    id: planId,
    strategy: "plan_tasks_only",
    constraints_snapshot: {
      timezone: "Asia/Shanghai",
      workday_start: "09:00:00",
      workday_end: "18:00:00",
      allowed_weekdays: [0, 1, 2, 3, 4, 5, 6],
    },
    decision_profile_snapshot: {},
    status: "draft",
    version,
    created_at: "2026-10-02T00:00:00Z",
    updated_at: "2026-10-02T00:00:00Z",
    expires_at: "2026-10-03T00:00:00Z",
    applied_at: null,
    abandoned_at: null,
    invalidated_at: null,
    invalidation_reason: "",
    items: [
      ...order.map((task_id, planning_order) => ({
        task_id,
        task_title: task_id === paperId ? "论文" : "Redis",
        task_version: 1,
        state: "placed",
        planning_order,
        start_at: task_id === paperId ? "2026-10-05T09:00:00Z" : "2026-10-05T10:00:00Z",
        end_at: task_id === paperId ? "2026-10-05T10:00:00Z" : "2026-10-05T11:00:00Z",
        reserved_start_at: task_id === paperId ? "2026-10-05T09:00:00Z" : "2026-10-05T10:00:00Z",
        reserved_end_at: task_id === paperId ? "2026-10-05T10:00:00Z" : "2026-10-05T11:00:00Z",
        locked: false,
        planned_duration_minutes: 60,
        reason_codes: [],
      })),
      { kind: "plan_evidence", evidence: { range_start: "2026-10-05T00:00:00Z", range_end: "2026-10-06T00:00:00Z" } },
    ],
  };
}

async function installApi(page: Page) {
  let currentPlan = draft();
  let acceptedOrder: string[] | null = null;
  let nextSubmitConflicts = false;
  let completionArtifactFailures = 0;
  let completionRequestCount = 0;
  let pendingCompletionArtifacts: Array<Record<string, unknown>> = [];
  const ensuredInteractionTypes: string[] = [];
  const interactionSubmitActions: string[] = [];
  const planEditValues: Array<{ task_id: string; start_at: string; end_at: string }> = [];
  const taskMutationMethods: string[] = [];

  await page.addInitScript(() => {
    window.localStorage.setItem("time-agent:onboarding:1:v1", "completed");
  });
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/api/v1/auth/me/") return route.fulfill({ json: { id: 1, email: "v3@example.test", display_name: "V3 Tester", is_staff: false } });
    if (path === "/api/v1/auth/csrf/") return route.fulfill({ json: { csrfToken: "v3-csrf" } });
    if (path === "/api/v1/preferences/me/") return route.fulfill({ json: {
      timezone: "Asia/Shanghai", locale: "zh-CN", workday_start: "09:00:00", workday_end: "18:00:00",
      sleep_start: "23:00:00", sleep_end: "07:00:00", default_event_duration_minutes: 60,
      preferred_focus_periods: [], default_reminder_offsets: [], weather_location: "", news_topics: [],
      briefing_time: "08:00:00", planning_rules: {}, updated_at: "2026-10-02T00:00:00Z",
    } });
    if (path === "/api/v1/today/") return route.fulfill({ json: {
      date: "2026-10-02", timezone: "Asia/Shanghai", generated_at: "2026-10-02T00:00:00Z",
      day_start_at: "2026-10-01T16:00:00Z", day_end_at: "2026-10-02T16:00:00Z",
      events: [], planned_tasks: [], due_tasks: [completionTask], overdue_tasks: [],
      unfinished_tasks: [completionTask], completed_tasks: [], pending_reminders: [],
      conflicts: [], next_event: null, minutes_until_next_event: null,
      execution_now: [], execution_next: [], execution_later: [{
        kind: "task", id: paperId, title: completionTask.title, start_at: null, end_at: null,
        status: "pending", due_at: completionTask.due_at,
      }],
    } });
    if (path === "/api/v1/briefings/runs/" && method === "GET") return route.fulfill({ json: [] });
    if (path === "/api/v1/tasks/" && method === "GET") return route.fulfill({ json: tasks });
    if (path === `/api/v1/tasks/${paperId}/complete/` && method === "POST") {
      completionRequestCount += 1;
      return route.fulfill({ json: { ...completionTask, status: "completed", completed_at: "2026-10-02T10:30:00Z" } });
    }
    if (path === `/api/v1/tasks/${paperId}/execution-summary/`) return route.fulfill({ json: {
      task_id: paperId, planned_seconds: 3600, active_seconds: 4500, evidence_status: "measured", signals: [],
    } });
    if (path === `/api/v1/tasks/${paperId}/`) return route.fulfill({ json: { ...completionTask, status: "completed", completed_at: "2026-10-02T10:30:00Z" } });
    if (path.startsWith("/api/v1/tasks/") && method !== "GET") taskMutationMethods.push(method);
    if (path === "/api/v1/planning/automation-policies/" && method === "GET") return route.fulfill({ json: [] });
    if (path.includes("/time-memory/me/capacity-forecast/")) return route.fulfill({ json: {
      range_start: "2026-10-02T00:00:00Z", range_end: "2026-10-09T00:00:00Z", available_minutes: 480,
      committed_minutes: 120, unplanned_minutes: 120, risk: "within_capacity", reason_codes: [],
    } });
    if (path === "/api/v1/planning/plans/" && method === "POST") return route.fulfill({ status: 201, json: currentPlan });
    if (path === `/api/v1/planning/plans/${planId}/` && method === "GET") return route.fulfill({ json: currentPlan });
    if (path === `/api/v1/planning/plans/${planId}/validate/` && method === "POST") return route.fulfill({ json: {
      plan: currentPlan, valid: true, reason_codes: [], checked_at: "2026-10-02T00:00:00Z",
    } });
    if (path === "/api/v1/interactions/" && method === "POST") {
      const body = request.postDataJSON() as { type: string; task_id?: string };
      ensuredInteractionTypes.push(body.type);
      if (body.type === "task_completion" && completionArtifactFailures > 0) {
        completionArtifactFailures -= 1;
        return route.fulfill({ status: 503, json: { detail: "Temporary interaction service failure" } });
      }
      if (body.type === "task_completion") {
        const artifact = {
        id: "44444444-4444-4444-8444-444444444443", conversation_id: null, agent_run_id: null,
        plan_id: null, plan_version: null, task_id: body.task_id ?? paperId, type: body.type,
        payload: { task_id: body.task_id ?? paperId }, allowed_actions: ["submit_feedback", "dismiss"],
        status: "pending", expires_at: "2026-10-16T00:00:00Z", version: 1,
        created_at: "2026-10-02T00:00:00Z", updated_at: "2026-10-02T00:00:00Z", resolved_at: null,
        };
        pendingCompletionArtifacts = [artifact, ...pendingCompletionArtifacts.filter((item) => item.id !== artifact.id)];
        return route.fulfill({ json: artifact });
      }
      const id = body.type === "priority_ranking"
        ? "44444444-4444-4444-8444-444444444441"
        : "44444444-4444-4444-8444-444444444442";
      return route.fulfill({ json: {
        id, conversation_id: null, agent_run_id: null, plan_id: planId, plan_version: currentPlan.version,
        task_id: null, type: body.type, payload: { plan_id: planId }, allowed_actions: ["edit", "reorder", "dismiss"],
        status: "pending", expires_at: "2026-10-03T00:00:00Z", version: 1,
        created_at: "2026-10-02T00:00:00Z", updated_at: "2026-10-02T00:00:00Z", resolved_at: null,
      } });
    }
    if (path === "/api/v1/interactions/" && method === "GET") {
      return route.fulfill({ json: url.searchParams.get("type") === "task_completion" ? pendingCompletionArtifacts : [] });
    }
    if (path === "/api/v1/interactions/telemetry/") return route.fulfill({ status: 202, body: "" });
    if (path.includes("/api/v1/interactions/") && path.endsWith("/submit/")) {
      const body = request.postDataJSON() as {
        action: string;
        values: { ordered_task_ids?: string[]; items?: Array<{ task_id: string; start_at: string; end_at: string }>; rating?: string; reason?: string };
      };
      interactionSubmitActions.push(body.action);
      const submittedInteractionId = path.split("/").filter(Boolean).at(-2) ?? "";
      if (body.action === "dismiss") {
        pendingCompletionArtifacts = pendingCompletionArtifacts.filter((item) => item.id !== submittedInteractionId);
      }
      if (nextSubmitConflicts) {
        nextSubmitConflicts = false;
        currentPlan = draft(currentPlan.version + 1);
        return route.fulfill({ status: 409, json: { detail: "Schedule plan version conflict" } });
      }
      if (body.action === "reorder" && body.values.ordered_task_ids) {
        acceptedOrder = body.values.ordered_task_ids;
        currentPlan = draft(currentPlan.version + 1, acceptedOrder);
      }
      if (body.action === "edit" && body.values.items?.length) {
        planEditValues.push(...body.values.items);
        const edits = new Map(body.values.items.map((item) => [item.task_id, item]));
        currentPlan = {
          ...currentPlan,
          version: currentPlan.version + 1,
          items: currentPlan.items.map((item) => {
            const edit = edits.get((item as { task_id?: string }).task_id ?? "");
            return edit ? { ...item, start_at: edit.start_at, end_at: edit.end_at } : item;
          }),
        };
      }
      const interactionType = submittedInteractionId === "44444444-4444-4444-8444-444444444441"
        ? "priority_ranking"
        : submittedInteractionId === "44444444-4444-4444-8444-444444444443"
          ? "task_completion"
          : "plan_timeline_edit";
      return route.fulfill({ json: {
        accepted: true, detail: null,
        interaction: {
          id: submittedInteractionId,
          conversation_id: null, agent_run_id: null, plan_id: interactionType === "task_completion" ? null : planId, plan_version: interactionType === "task_completion" ? null : currentPlan.version,
          task_id: interactionType === "task_completion" ? paperId : null, type: interactionType, payload: interactionType === "task_completion" ? { task_id: paperId, ...(body.action === "submit_feedback" ? { completion_feedback: body.values } : {}) } : { plan_id: planId },
          allowed_actions: ["edit", "reorder", "dismiss"], status: "pending", expires_at: "2026-10-03T00:00:00Z",
          version: 2, created_at: "2026-10-02T00:00:00Z", updated_at: "2026-10-02T00:00:00Z", resolved_at: null,
        },
        plan: currentPlan, reason_codes: [], conflicts: [], candidate: null, replayed: false,
      } });
    }
    if (path === "/api/v1/integrations/calendar/connections/" || path === "/api/v1/insights/" || path.startsWith("/api/v1/events/")) {
      return route.fulfill({ json: [] });
    }
    return route.fulfill({ json: [] });
  });

  return {
    acceptedOrder: () => acceptedOrder,
    planEditValues,
    taskMutationMethods: () => taskMutationMethods,
    ensuredInteractionTypes,
    completionArtifactEnsureRequests: () => ensuredInteractionTypes.filter((type) => type === "task_completion").length,
    interactionSubmitActions,
    makeNextSubmitConflict: () => { nextSubmitConflicts = true; },
    failCompletionArtifactEnsures: (count: number) => { completionArtifactFailures = count; },
    completionRequests: () => completionRequestCount,
    setPendingCompletionArtifacts: (items: Array<Record<string, unknown>>) => { pendingCompletionArtifacts = items; },
  };
}

async function openDraft(page: Page) {
  await page.getByRole("button", { name: "高级规划设置" }).click();
  await page.getByRole("checkbox", { name: "论文" }).check();
  await page.getByRole("checkbox", { name: "Redis" }).check();
  await page.getByRole("button", { name: "生成草案" }).click();
  await expect(page.getByRole("button", { name: "调整本次任务顺序" })).toBeVisible();
}

for (const width of [320, 375, 430]) {
  test(`supports keyboard plan ranking without overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const api = await installApi(page);
    await page.goto("/planning");

    await page.getByRole("button", { name: "高级规划设置" }).click();
    await page.getByRole("checkbox", { name: "论文" }).check();
    await page.getByRole("checkbox", { name: "Redis" }).check();
    await page.getByRole("button", { name: "生成草案" }).click();
    await page.getByRole("button", { name: "调整本次任务顺序" }).click();
    const ranker = page.getByRole("region", { name: "本次计划优先顺序" });
    await expect(ranker).toBeVisible();
    await expect(ranker.getByRole("button", { name: "拖动排序：论文，当前第 1 项" })).toBeVisible();
    await expect(page.getByRole("region", { name: "可编辑计划时间线" })).toHaveCount(0);

    const moveUp = ranker.getByRole("button", { name: "上移：Redis" });
    await moveUp.focus();
    await page.keyboard.press("Enter");
    await expect(ranker.getByRole("status").filter({ hasText: "永久优先级没有更改" })).toBeVisible();
    await expect.poll(api.acceptedOrder).toEqual([redisId, paperId]);
    await expect.poll(async () => page.locator(`#priority-handle-${redisId}`).evaluate((element) => document.activeElement === element)).toBe(true);
    await expect.poll(api.taskMutationMethods).toEqual([]);

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

test("supports pointer dragging a task into a new priority order", async ({ page }, testInfo: TestInfo) => {
  test.skip(testInfo.project.name !== "chromium", "Mouse pointer drag is checked in the desktop browser project.");
  await installApi(page);
  await page.goto("/planning");
  await openDraft(page);
  await page.getByRole("button", { name: "调整本次任务顺序" }).click();

  const source = page.getByRole("button", { name: "拖动排序：论文，当前第 1 项" });
  const target = page.getByRole("button", { name: "拖动排序：Redis，当前第 2 项" });
  const start = await source.boundingBox();
  const end = await target.boundingBox();
  expect(start).not.toBeNull();
  expect(end).not.toBeNull();
  await page.mouse.move(start!.x + start!.width / 2, start!.y + start!.height / 2);
  await page.mouse.down();
  await page.mouse.move(end!.x + end!.width / 2, end!.y + end!.height / 2, { steps: 8 });
  await page.mouse.up();

  await expect.poll(async () => page.getByRole("button", { name: "拖动排序：Redis，当前第 1 项" }).count()).toBe(1);
  await expect(page.getByRole("status").filter({ hasText: "永久优先级没有更改" })).toBeVisible();
});

test("supports touch dragging a task into a new priority order", async ({ page }, testInfo: TestInfo) => {
  test.skip(testInfo.project.name !== "mobile-chromium", "Touch drag is checked in the mobile browser project.");
  await installApi(page);
  await page.goto("/planning");
  await openDraft(page);
  await page.getByRole("button", { name: "调整本次任务顺序" }).click();

  const source = page.getByRole("button", { name: "拖动排序：论文，当前第 1 项" });
  const target = page.getByRole("button", { name: "拖动排序：Redis，当前第 2 项" });
  await target.scrollIntoViewIfNeeded();
  const start = await source.boundingBox();
  const end = await target.boundingBox();
  expect(start).not.toBeNull();
  expect(end).not.toBeNull();
  const session = await page.context().newCDPSession(page);
  const touchPoint = (x: number, y: number) => ({ x, y, id: 1, radiusX: 4, radiusY: 4, force: 1 });
  await session.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [touchPoint(start!.x + start!.width / 2, start!.y + start!.height / 2)],
  });
  await page.waitForTimeout(80);
  for (let step = 1; step <= 8; step += 1) {
    const progress = step / 8;
    await session.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [touchPoint(
        start!.x + start!.width / 2 + (end!.x + end!.width / 2 - start!.x - start!.width / 2) * progress,
        start!.y + start!.height / 2 + (end!.y + end!.height / 2 - start!.y - start!.height / 2) * progress,
      )],
    });
    await page.waitForTimeout(20);
  }
  await session.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await session.detach();

  await expect(page.getByRole("status").filter({ hasText: "永久优先级没有更改" })).toBeVisible();
  await expect(page.getByRole("button", { name: "拖动排序：Redis，当前第 1 项" })).toBeVisible();
});

test("supports keyboard time adjustment and submits the edited draft to the backend", async ({ page }, testInfo: TestInfo) => {
  const api = await installApi(page);
  await page.goto("/planning");
  await openDraft(page);
  await page.getByRole("button", { name: "调整时间与时长" }).click();

  const mobile = testInfo.project.name === "mobile-chromium";
  const editor = mobile
    ? page.getByRole("dialog", { name: "调整时间：论文" })
    : page.getByRole("region", { name: "可编辑计划时间线" });
  if (mobile) {
    const paper = page.getByRole("region", { name: "可编辑计划时间线" }).getByRole("listitem").filter({ hasText: "论文" });
    await paper.getByRole("button", { name: "调整时间", exact: true }).click();
  }

  const moveLater = mobile
    ? editor.getByRole("button", { name: "推后 15 分钟" })
    : editor.getByRole("button", { name: "推后 15 分钟：论文" });
  await moveLater.focus();
  await page.keyboard.press("Enter");
  const save = mobile ? editor.getByRole("button", { name: "保存调整" }) : editor.getByRole("button", { name: "保存" }).first();
  await save.focus();
  await page.keyboard.press("Enter");

  await expect.poll(() => api.planEditValues.length).toBe(1);
  expect(api.planEditValues[0]).toMatchObject({
    task_id: paperId,
    start_at: "2026-10-05T09:15:00.000Z",
    end_at: "2026-10-05T10:15:00.000Z",
  });
  await expect(page.getByRole("status").filter({ hasText: "计划仍是草案" })).toBeVisible();
});

test("uses a mobile sheet to adjust one placed plan item", async ({ page }, testInfo: TestInfo) => {
  test.skip(testInfo.project.name !== "mobile-chromium", "Mobile plan editing uses the touch-sized adjustment sheet.");
  await page.setViewportSize({ width: 393, height: 844 });
  const api = await installApi(page);
  await page.goto("/planning");
  await openDraft(page);
  await page.getByRole("button", { name: "调整时间与时长" }).click();

  const timeline = page.getByRole("region", { name: "可编辑计划时间线" });
  const paper = timeline.getByRole("listitem").filter({ hasText: "论文" });
  await paper.getByRole("button", { name: "调整时间", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "调整时间：论文" });
  await expect(editor).toBeVisible();
  await page.screenshot({ path: "../docs/mobile-ui/evidence/iteration-3-planning-edit-393.png" });
  await page.setViewportSize({ width: 320, height: 800 });
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 320);
  await page.setViewportSize({ width: 393, height: 844 });
  await editor.getByRole("button", { name: "推后 15 分钟" }).click();
  await editor.getByRole("button", { name: "保存调整" }).click();

  await expect.poll(() => api.planEditValues.length).toBe(1);
  expect(api.planEditValues[0]).toMatchObject({
    task_id: paperId,
    start_at: "2026-10-05T09:15:00.000Z",
    end_at: "2026-10-05T10:15:00.000Z",
  });
  await expect(editor).toHaveCount(0);
});

test("opens only the requested planning interaction and lets the user resume it later", async ({ page }) => {
  const api = await installApi(page);
  await page.goto("/planning");
  await openDraft(page);

  expect(api.ensuredInteractionTypes).toEqual([]);
  await page.getByRole("button", { name: "调整时间与时长" }).click();
  const timeline = page.getByRole("region", { name: "可编辑计划时间线" });
  await expect(timeline).toBeVisible();
  await expect(timeline).toBeFocused();
  await expect.poll(() => api.ensuredInteractionTypes).toEqual(["plan_timeline_edit"]);

  await page.getByRole("button", { name: "稍后再处理" }).click();
  const reopenTimeline = page.getByRole("button", { name: "调整时间与时长" });
  await expect(reopenTimeline).toBeVisible();
  await expect(reopenTimeline).toBeFocused();
  expect(api.interactionSubmitActions).toEqual([]);
  await page.getByRole("button", { name: "调整时间与时长" }).click();
  await expect(page.getByRole("region", { name: "可编辑计划时间线" })).toBeVisible();
  expect(api.ensuredInteractionTypes).toEqual(["plan_timeline_edit"]);
});

test("automatically refreshes the plan after a stale interaction conflict", async ({ page }, testInfo: TestInfo) => {
  const api = await installApi(page);
  await page.goto("/planning");
  await openDraft(page);
  await page.getByRole("button", { name: "调整时间与时长" }).click();
  api.makeNextSubmitConflict();

  if (testInfo.project.name === "mobile-chromium") {
    const timeline = page.getByRole("region", { name: "可编辑计划时间线" });
    const paper = timeline.getByRole("listitem").filter({ hasText: "论文" });
    await paper.getByRole("button", { name: "调整时间", exact: true }).click();
    await page.getByRole("dialog", { name: "调整时间：论文" }).getByRole("button", { name: "保存调整" }).click();
  } else {
    await page.getByRole("button", { name: "保存" }).first().click();
  }
  await expect(page.getByRole("button", { name: "重试同步" })).toHaveCount(0);
  if (testInfo.project.name === "mobile-chromium") {
    const editor = page.getByRole("dialog", { name: "调整时间：论文" });
    await expect(editor).toBeVisible();
    await expect(editor.getByRole("status").filter({ hasText: "计划刚刚更新，已载入最新版本" })).toBeVisible();
  } else {
    await expect(page.getByText("计划刚刚更新，已载入最新版本。请检查后继续。")).toBeVisible();
    await expect(page.getByRole("region", { name: "可编辑计划时间线" })).toBeVisible();
  }
});

test("supports pointer dragging a timeline block and submits the edited draft", async ({ page }, testInfo: TestInfo) => {
  test.skip(testInfo.project.name !== "chromium", "Mouse timeline drag is checked in the desktop browser project.");
  const api = await installApi(page);
  await page.goto("/planning");
  await openDraft(page);
  await page.getByRole("button", { name: "调整时间与时长" }).click();

  const handle = page.getByRole("button", { name: "拖动调整时间：论文" });
  await handle.evaluate((element) => element.scrollIntoView({ block: "center", behavior: "instant" }));
  const box = await handle.boundingBox();
  expect(box).not.toBeNull();
  const x = box!.x + box!.width / 2;
  const y = box!.y + box!.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y + 32, { steps: 6 });
  await page.mouse.up();

  await expect.poll(() => api.planEditValues.length).toBe(1);
  expect(api.planEditValues[0]).toMatchObject({ start_at: "2026-10-05T09:15:00.000Z" });
  await expect.poll(async () => page.locator(`#timeline-handle-${paperId}`).evaluate((element) => document.activeElement === element)).toBe(true);
});

test("supports touch dragging a timeline block and submits the edited draft", async ({ page }, testInfo: TestInfo) => {
  test.skip(testInfo.project.name !== "mobile-chromium", "Touch timeline drag is checked in the mobile browser project.");
  const api = await installApi(page);
  await page.goto("/planning");
  await openDraft(page);
  await page.getByRole("button", { name: "调整时间与时长" }).click();

  const handle = page.getByRole("button", { name: "拖动调整时间：论文" });
  await handle.evaluate((element) => element.scrollIntoView({ block: "center", behavior: "instant" }));
  const box = await handle.boundingBox();
  expect(box).not.toBeNull();
  const session = await page.context().newCDPSession(page);
  const touchPoint = (x: number, y: number) => ({ x, y, id: 1, radiusX: 4, radiusY: 4, force: 1 });
  const x = box!.x + box!.width / 2;
  const y = box!.y + box!.height / 2;
  await session.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [touchPoint(x, y)] });
  await page.waitForTimeout(80);
  for (let step = 1; step <= 6; step += 1) {
    await session.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [touchPoint(x, y + (32 * step) / 6)],
    });
    await page.waitForTimeout(20);
  }
  await session.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await session.detach();

  await expect.poll(() => api.planEditValues.length).toBe(1);
  expect(api.planEditValues[0]).toMatchObject({ start_at: "2026-10-05T09:15:00.000Z" });
});

test("keeps completion feedback optional, reveals reasons progressively, and respects reduced motion", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await installApi(page);
  await page.goto("/today");

  if (testInfo.project.name === "mobile-chromium") {
    await page.getByText("稍后 · 1 项").click();
  }
  await page.getByRole("button", { name: "完成任务：论文" }).first().click();
  const checkIn = page.getByRole("region", { name: "任务完成反馈" });
  await expect(checkIn).toBeVisible();
  await expect.poll(async () => checkIn.getByRole("heading").evaluate((element) => document.activeElement === element)).toBe(true);
  await expect(checkIn.getByText("计划时长：60 分钟")).toBeVisible();
  await expect(checkIn.getByText("实际投入：75 分钟")).toBeVisible();
  await expect(checkIn.getByRole("button", { name: "跳过" })).toBeVisible();
  await expect(checkIn.getByRole("button", { name: "补充原因（可选）" })).toBeVisible();
  await expect(checkIn.getByLabel("补充原因（可选）")).toHaveCount(0);

  await checkIn.getByRole("button", { name: "差不多" }).click();
  await checkIn.getByRole("button", { name: "记录反馈" }).click();
  const savedStatus = checkIn.getByText("已记录：差不多");
  await expect(savedStatus).toBeVisible();
  await expect.poll(async () => savedStatus.evaluate((element) => document.activeElement === element)).toBe(true);
  const icon = checkIn.locator("svg").first();
  await expect.poll(() => icon.evaluate((element) => getComputedStyle(element).animationName)).toBe("none");
  await checkIn.getByRole("button", { name: "完成" }).click();
  const dismissed = page.locator("#today-completion-feedback-dismissed");
  await expect(dismissed).toBeVisible();
  await expect.poll(async () => dismissed.evaluate((element) => document.activeElement === element)).toBe(true);
});

test("recovers a completion feedback card after a temporary service failure and page reload", async ({ page }, testInfo) => {
  const api = await installApi(page);
  api.failCompletionArtifactEnsures(2);
  await page.goto("/today");
  if (testInfo.project.name === "mobile-chromium") {
    await page.getByText("稍后 · 1 项").click();
  }
  await page.getByRole("button", { name: "完成任务：论文" }).first().click();

  await expect(page.getByRole("status").filter({ hasText: "反馈卡暂时不可用" })).toBeVisible();
  expect(api.completionRequests()).toBe(1);
  await expect.poll(() => api.completionArtifactEnsureRequests()).toBe(2);
  await page.reload();

  await expect.poll(() => api.completionArtifactEnsureRequests()).toBe(3);
  await expect(page.getByRole("region", { name: "任务完成反馈" })).toBeVisible({ timeout: 15_000 });
  expect(api.completionRequests()).toBe(1);
});

test("queues unfinished completion feedback one card at a time", async ({ page }) => {
  const api = await installApi(page);
  api.setPendingCompletionArtifacts([
    {
      id: "44444444-4444-4444-8444-444444444443", conversation_id: null, agent_run_id: null,
      plan_id: null, plan_version: null, task_id: paperId, type: "task_completion", payload: { task_id: paperId },
      allowed_actions: ["submit_feedback", "dismiss"], status: "pending", expires_at: "2026-10-16T00:00:00Z", version: 1,
      created_at: "2026-10-02T00:00:00Z", updated_at: "2026-10-02T00:00:00Z", resolved_at: null,
    },
    {
      id: "55555555-5555-4555-8555-555555555555", conversation_id: null, agent_run_id: null,
      plan_id: null, plan_version: null, task_id: redisId, type: "task_completion", payload: { task_id: redisId },
      allowed_actions: ["submit_feedback", "dismiss"], status: "pending", expires_at: "2026-10-16T00:00:00Z", version: 1,
      created_at: "2026-10-02T00:00:00Z", updated_at: "2026-10-02T00:00:00Z", resolved_at: null,
    },
  ]);
  await page.goto("/today");

  await expect(page.getByRole("region", { name: "任务完成反馈" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "查看下一项" })).toBeVisible();
  await page.getByRole("button", { name: "查看下一项" }).click();
  await expect(page.getByRole("region", { name: "任务完成反馈" })).toHaveCount(1);
  await expect(page.locator("#completion-feedback-heading-55555555-5555-4555-8555-555555555555")).toBeVisible();
});
