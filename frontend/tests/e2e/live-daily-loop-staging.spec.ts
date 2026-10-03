import { expect, test, type Page, type Route } from "@playwright/test";

const email = process.env.TIME_AGENT_E2E_EMAIL;
const password = process.env.TIME_AGENT_E2E_PASSWORD;
const stageUrl = "http://127.0.0.1:7081";

test.skip(
  !email || !password || process.env.TIME_AGENT_E2E_BASE_URL !== stageUrl,
  "This real-backend Daily Loop gate is restricted to local staging at 127.0.0.1:7081.",
);

type TaskRecord = {
  id: string;
  title: string;
  status: string;
  due_at: string | null;
  planned_start_at: string | null;
  planned_end_at: string | null;
};
type TodaySummary = {
  date: string;
  timezone: string;
  execution_now: Array<{ id: string; title: string }>;
  execution_next: Array<{ id: string; title: string }>;
  execution_later: Array<{ id: string; title: string }>;
  completed_tasks: Array<{ id: string; title: string }>;
};
type SchedulePlan = {
  id: string;
  status: string;
  version: number;
  items: Array<{ kind?: string; task_id?: string; state?: string }>;
};
type PlanCreateRequest = {
  task_ids: string[];
  operation_id: string;
  range_start: string;
  range_end: string;
  strategy: "plan_tasks_only";
  ordering: "priority_deadline";
};

async function getJson<T>(page: Page, path: string): Promise<T> {
  const result = await page.evaluate(async (requestPath) => {
    const response = await fetch(requestPath, { credentials: "same-origin", headers: { Accept: "application/json" } });
    return { status: response.status, body: await response.json() as unknown };
  }, path);
  if (result.status < 200 || result.status >= 300) {
    throw new Error(`Staging API read failed (${result.status}): ${path}`);
  }
  return result.body as T;
}

async function postJson<T>(page: Page, path: string, body: unknown): Promise<{ status: number; body: T }> {
  return page.evaluate(async ({ requestPath, requestBody }) => {
    const csrfToken = document.cookie.split(";")
      .map((cookie) => cookie.trim())
      .find((cookie) => cookie.startsWith("csrftoken="))
      ?.slice("csrftoken=".length);
    const response = await fetch(requestPath, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(csrfToken ? { "X-CSRFToken": decodeURIComponent(csrfToken) } : {}),
      },
      body: JSON.stringify(requestBody),
    });
    return { status: response.status, body: await response.json() as T };
  }, { requestPath: path, requestBody: body });
}

function localDateTime(offsetMinutes: number, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(Date.now() + offsetMinutes * 60_000));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}

async function createTask(page: Page, title: string, timezone: string, startOffset: number, endOffset: number) {
  await page.goto("/tasks");
  await page.getByRole("button", { name: "新建任务" }).click();
  await page.getByLabel("任务标题").fill(title);
  await page.getByLabel("项目").fill("V4 synthetic Daily Loop evidence");
  await page.getByLabel("预计时长（分钟）").fill("30");
  await page.getByLabel(`计划开始（${timezone}）`).fill(localDateTime(startOffset, timezone));
  await page.getByLabel(`计划结束（${timezone}）`).fill(localDateTime(endOffset, timezone));
  await page.getByRole("button", { name: "创建任务" }).click();
  await expect(page.getByRole("dialog", { name: "创建任务" })).toHaveCount(0);
  await expect.poll(async () => (await getJson<TaskRecord[]>(page, "/api/v1/tasks/")).some((task) => task.title === title))
    .toBeTruthy();
}

async function passivelyCaptureFirstCommitThenFailClient(route: Route, captures: PlanCreateRequest[]) {
  const requestBody = route.request().postDataJSON() as PlanCreateRequest;
  captures.push(requestBody);
  const committedResponse = await route.fetch();
  expect(committedResponse.ok()).toBeTruthy();
  await route.abort("failed");
}

test("real browser completes Today execution, Harvest, Day Closing and a retry-safe tomorrow draft", async ({ page }) => {
  test.setTimeout(6 * 60_000);
  const journeyMetrics = {
    pageTransitions: 0,
    clicks: 0,
    textInputs: 0,
    agentTurns: 0,
    toolCalls: 0,
    clarifications: 0,
    approvals: 0,
    failedRequests: 0,
    httpErrors: 0,
    recoveries: 0,
  };
  await page.exposeFunction("__recordV4DailyLoopInput", (kind: string) => {
    if (kind === "click") journeyMetrics.clicks += 1;
    if (kind === "input") journeyMetrics.textInputs += 1;
  });
  await page.addInitScript(() => {
    const report = (window as Window & { __recordV4DailyLoopInput?: (kind: string) => void }).__recordV4DailyLoopInput;
    document.addEventListener("click", () => report?.("click"), true);
    document.addEventListener("input", () => report?.("input"), true);
  });
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) journeyMetrics.pageTransitions += 1;
  });
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/chat\/.*\/messages\/?/.test(new URL(request.url()).pathname)) journeyMetrics.agentTurns += 1;
    if (request.method() === "POST" && /\/tools\//.test(new URL(request.url()).pathname)) journeyMetrics.toolCalls += 1;
  });
  page.on("requestfailed", () => { journeyMetrics.failedRequests += 1; });
  page.on("response", (response) => {
    if (response.status() >= 400) journeyMetrics.httpErrors += 1;
  });
  const runId = crypto.randomUUID().slice(0, 8);
  const titles = {
    now: `[V4 daily loop ${runId}] 当前执行`,
    next: `[V4 daily loop ${runId}] 下一项`,
    later: `[V4 daily loop ${runId}] 稍后项`,
  };

  await page.addInitScript(() => {
    window.localStorage.setItem("time-agent:onboarding:1:v1", "completed");
  });
  await page.goto("/login");
  await page.getByLabel("邮箱").fill(email as string);
  await page.getByLabel("密码").fill(password as string);
  await page.getByRole("button", { name: "登录", exact: true }).last().click();
  await expect(page).toHaveURL(/\/today$/);
  const onboarding = page.getByRole("dialog", { name: "欢迎使用 Time Agent" });
  if (await onboarding.isVisible().catch(() => false)) {
    await onboarding.getByRole("button", { name: "暂时跳过" }).click();
  }

  const initialToday = await getJson<TodaySummary>(page, "/api/v1/today/");
  const timezone = initialToday.timezone;
  const originalEvents = await getJson<Array<{ id: string }>>(page, "/api/v1/events/");
  const existingPlans = await getJson<SchedulePlan[]>(page, "/api/v1/planning/plans/");

  await createTask(page, titles.now, timezone, -10, 70);
  await createTask(page, titles.next, timezone, 80, 100);
  await createTask(page, titles.later, timezone, 110, 130);

  const tasksAfterCreate = await getJson<TaskRecord[]>(page, "/api/v1/tasks/");
  const testTasks = Object.values(titles).map((title) => {
    const record = tasksAfterCreate.find((task) => task.title === title);
    expect(record, `Expected test task ${title} to be visible from the real Task API`).toBeTruthy();
    return record as TaskRecord;
  });
  const generatedTaskIds = new Set(testTasks.map((task) => task.id));

  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "今天", exact: true })).toBeVisible();
  const todayBeforeExecution = await getJson<TodaySummary>(page, "/api/v1/today/");
  expect(todayBeforeExecution.execution_now.some((item) => item.title === titles.now)).toBeTruthy();
  expect(todayBeforeExecution.execution_next.length).toBeGreaterThan(0);
  expect([...todayBeforeExecution.execution_next, ...todayBeforeExecution.execution_later]
    .some((item) => item.title === titles.next)).toBeTruthy();
  expect(todayBeforeExecution.execution_later.some((item) => item.title === titles.later)).toBeTruthy();
  await expect(page.locator('section[aria-label="现在"]:visible').getByText(titles.now)).toBeVisible();
  await expect(page.locator('section[aria-label="接下来"]:visible').getByText(todayBeforeExecution.execution_next[0].title)).toBeVisible();
  const nextBucket = todayBeforeExecution.execution_next.some((item) => item.title === titles.next) ? "接下来" : "稍后";
  await expect(page.locator(`section[aria-label="${nextBucket}"]:visible`).getByText(titles.next)).toBeVisible();
  await expect(page.locator('section[aria-label="稍后"]:visible').getByText(titles.later)).toBeVisible();

  await page.locator(`button[aria-label="开始任务：${titles.now}"]:visible`).click();
  await expect.poll(async () => {
    const summary = await getJson<TodaySummary>(page, "/api/v1/today/");
    return summary.execution_now.some((item) => item.title === titles.now);
  }).toBeTruthy();
  await page.locator(`button[aria-label="完成任务：${titles.now}"]:visible`).click();
  const harvest = page.getByRole("region", { name: "任务完成反馈" })
    .filter({ has: page.getByRole("heading", { name: titles.now, exact: true }) });
  await expect(harvest).toBeVisible();
  const aboutRightButton = harvest.getByRole("button", { name: "差不多" });
  await aboutRightButton.click();
  await expect(aboutRightButton).toHaveAttribute("aria-pressed", "true");
  await harvest.getByRole("button", { name: "记录反馈" }).click();
  await expect(harvest.getByText("反馈已记录，任务完成状态没有改变。", { exact: true })).toBeVisible();
  await expect.poll(async () => {
    const tasks = await getJson<TaskRecord[]>(page, "/api/v1/tasks/");
    return tasks.find((task) => task.title === titles.now)?.status;
  }).toBe("completed");

  await page.reload();
  const todayAfterReload = await getJson<TodaySummary>(page, "/api/v1/today/");
  const completedNow = todayAfterReload.completed_tasks.find((task) => task.title === titles.now);
  expect(completedNow).toBeTruthy();
  const closingPreview = page.getByRole("region", { name: "今天收尾与明日草案" });
  await expect(closingPreview.getByText(/已完成 \d+ 项/)).toBeVisible();

  await page.getByRole("button", { name: "整理明天" }).click();
  const closing = page.getByRole("region", { name: "今天收尾与明日草案" });
  await expect(closing.getByRole("heading", { name: "还没完成的事" })).toBeVisible();
  const nextTaskCheckbox = closing.getByRole("checkbox", { name: new RegExp(titles.next.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) });
  const laterTaskCheckbox = closing.getByRole("checkbox", { name: new RegExp(titles.later.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) });
  await nextTaskCheckbox.check();
  expect(await laterTaskCheckbox.isChecked()).toBe(false);

  const committedRequests: PlanCreateRequest[] = [];
  let failFirstCommittedResponse = true;
  await page.route("**/api/v1/planning/plans/", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    if (failFirstCommittedResponse) {
      failFirstCommittedResponse = false;
      await passivelyCaptureFirstCommitThenFailClient(route, committedRequests);
      return;
    }
    committedRequests.push(route.request().postDataJSON() as PlanCreateRequest);
    await route.continue();
  });

  const generateButton = closing.getByRole("button", { name: /生成草案/ });
  await generateButton.click();
  await expect(closing.getByRole("alert")).toHaveText("明日草案暂时没有生成。任务状态和日程没有因此改变，请重试。");
  const retryResponse = page.waitForResponse((response) => response.url().includes("/api/v1/planning/plans/") && response.request().method() === "POST");
  await generateButton.click();
  const firstPlan = await (await retryResponse).json() as SchedulePlan;
  journeyMetrics.recoveries += 1;
  expect(firstPlan.status).toBe("draft");
  expect(committedRequests).toHaveLength(2);
  expect(committedRequests[0].operation_id).toBe(committedRequests[1].operation_id);
  expect(committedRequests[0].task_ids).toEqual(committedRequests[1].task_ids);
  await page.unroute("**/api/v1/planning/plans/");

  const plansAfterFirstRetry = await getJson<SchedulePlan[]>(page, "/api/v1/planning/plans/");
  const newPlansAfterFirstRetry = plansAfterFirstRetry.filter((plan) => !existingPlans.some((existing) => existing.id === plan.id));
  expect(newPlansAfterFirstRetry.filter((plan) => plan.id === firstPlan.id)).toHaveLength(1);
  const mismatch = await postJson<{ detail?: string }>(page, "/api/v1/planning/plans/", {
    ...committedRequests[0],
    task_ids: [...testTasks.filter((task) => task.title !== titles.now).map((task) => task.id)].sort(),
  });
  expect(mismatch.status).toBe(400);

  const allTaskRecordsAfterFirstPlan = await getJson<TaskRecord[]>(page, "/api/v1/tasks/");
  const generatedAfterFirstPlan = allTaskRecordsAfterFirstPlan.filter((task) => generatedTaskIds.has(task.id));
  for (const task of generatedAfterFirstPlan) {
    const before = testTasks.find((candidate) => candidate.id === task.id) as TaskRecord;
    expect(task.planned_start_at).toBe(before.planned_start_at);
    expect(task.planned_end_at).toBe(before.planned_end_at);
    expect(task.due_at).toBe(before.due_at);
  }
  expect(await getJson<Array<{ id: string }>>(page, "/api/v1/events/")).toEqual(originalEvents);

  const firstPlanView = await getJson<SchedulePlan>(page, `/api/v1/planning/plans/${firstPlan.id}/`);
  const unplaced = firstPlanView.items.filter((item) => item.kind !== "plan_evidence" && item.state === "unplaced");
  if (unplaced.length > 0) {
    await expect(closing.getByRole("region", { name: "明日安排取舍" })).toBeVisible();
    await expect(closing.getByText("有任务尚未找到合适时段；它们仍在草案中标记为未安排，没有被删除或延期。", { exact: true })).toBeVisible();
  }

  const abandonDraftButton = unplaced.length > 0 ? "放弃草案并全部重选" : "放弃草案并重新选择";
  await closing.getByRole("button", { name: abandonDraftButton }).click();
  await expect(closing.getByText("草案已放弃；任务仍保留在任务列表中。")).toBeVisible();
  const nowTaskCheckbox = closing.getByRole("checkbox", { name: new RegExp(titles.later.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) });
  await nowTaskCheckbox.check();
  const secondPlanResponse = page.waitForResponse((response) => response.url().includes("/api/v1/planning/plans/") && response.request().method() === "POST");
  const secondPlanRequest = page.waitForRequest((request) => request.url().includes("/api/v1/planning/plans/") && request.method() === "POST");
  await closing.getByRole("button", { name: /生成草案/ }).click();
  const secondPlan = await (await secondPlanResponse).json() as SchedulePlan;
  const secondOperation = secondPlanRequest.then((request) => request.postDataJSON() as PlanCreateRequest);
  expect(secondPlan.id).not.toBe(firstPlan.id);
  expect((await secondOperation).operation_id).not.toBe(committedRequests[0].operation_id);
  expect(secondPlan.status).toBe("draft");

  await page.reload();
  const recoveredClosing = page.getByRole("region", { name: "今天收尾与明日草案" });
  await expect(recoveredClosing.getByRole("link", { name: /检查草案|手动调整草案/ }))
    .toHaveAttribute("href", `/planning?plan_id=${secondPlan.id}`);
  const recoveredPlan = await getJson<SchedulePlan>(page, `/api/v1/planning/plans/${secondPlan.id}/`);
  expect(recoveredPlan.status).toBe("draft");

  const finalToday = await getJson<TodaySummary>(page, "/api/v1/today/");
  expect(finalToday.completed_tasks.some((task) => task.id === completedNow?.id)).toBe(true);
  const finalTasks = await getJson<TaskRecord[]>(page, "/api/v1/tasks/");
  for (const task of finalTasks.filter((candidate) => generatedTaskIds.has(candidate.id))) {
    const before = testTasks.find((candidate) => candidate.id === task.id) as TaskRecord;
    expect(task.due_at).toBe(before.due_at);
    expect(task.planned_start_at).toBe(before.planned_start_at);
    expect(task.planned_end_at).toBe(before.planned_end_at);
    if (task.id !== completedNow?.id) expect(task.status).toBe("pending");
  }
  expect((await getJson<Array<{ id: string }>>(page, "/api/v1/events/")).map((event) => event.id).sort())
    .toEqual(originalEvents.map((event) => event.id).sort());
  const finalPlans = await getJson<SchedulePlan[]>(page, "/api/v1/planning/plans/");
  const currentRunPlans = finalPlans.filter((plan) => !existingPlans.some((existing) => existing.id === plan.id));
  expect(currentRunPlans.filter((plan) => plan.id === firstPlan.id)).toHaveLength(1);
  expect(currentRunPlans.filter((plan) => plan.id === secondPlan.id)).toHaveLength(1);
  expect(currentRunPlans.find((plan) => plan.id === secondPlan.id)?.status).toBe("draft");
  test.info().annotations.push({
    type: "scripted-journey-friction",
    description: JSON.stringify(journeyMetrics),
  });
  console.log(`V4_DAILY_LOOP_METRICS=${JSON.stringify(journeyMetrics)}`);
});
