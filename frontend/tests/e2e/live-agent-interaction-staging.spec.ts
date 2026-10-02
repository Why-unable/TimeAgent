import { expect, test, type Page } from "@playwright/test";

const email = process.env.TIME_AGENT_E2E_EMAIL;
const password = process.env.TIME_AGENT_E2E_PASSWORD;
const enabled = process.env.TIME_AGENT_E2E_ENABLE_INTERACTIONS === "1";
const stageUrl = "http://127.0.0.1:7081";

test.skip(
  !enabled || !email || !password || process.env.TIME_AGENT_E2E_BASE_URL !== stageUrl,
  "This live Agent interaction regression is restricted to local V3 staging at 127.0.0.1:7081.",
);

type TaskRecord = {
  id: string;
  title: string;
  status: string;
  priority: string;
  planned_start_at?: string | null;
  planned_end_at?: string | null;
};
type PlanItem = { task_id?: string; kind?: string; state?: string; planning_order?: number };
type SchedulePlan = { id: string; status: string; version: number; items: PlanItem[] };
type TodaySummary = { planned_tasks: Array<{ id: string }> };

async function getJson<T>(page: Page, path: string): Promise<T> {
  const result = await page.evaluate(async (requestPath) => {
    const response = await fetch(requestPath, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    return { status: response.status, body: await response.json() as unknown };
  }, path);
  if (result.status < 200 || result.status >= 300) {
    throw new Error("Read-only staging API request failed (" + result.status + "): " + path);
  }
  return result.body as T;
}

function shanghaiDateOffset(offset: number): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const date = new Date(Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day) + offset));
  return date.getUTCFullYear() + "-" + String(date.getUTCMonth() + 1).padStart(2, "0") + "-" + String(date.getUTCDate()).padStart(2, "0");
}

function nextShanghaiWeekday(): string {
  for (let offset = 1; offset <= 7; offset += 1) {
    const date = shanghaiDateOffset(offset);
    const [year, month, day] = date.split("-").map(Number);
    const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
    if (weekday !== 0 && weekday !== 6) return date;
  }
  throw new Error("Could not find the next Shanghai weekday.");
}

function localInput(value: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return values.year + "-" + values.month + "-" + values.day + "T" + values.hour + ":" + values.minute;
}

function orderedTaskIds(plan: SchedulePlan): string[] {
  return plan.items
    .filter((item) => item.kind !== "plan_evidence" && item.state !== "unplaced" && item.task_id)
    .map((item, index) => ({ id: item.task_id as string, order: item.planning_order ?? index }))
    .sort((left, right) => left.order - right.order)
    .map((item) => item.id);
}

async function latestConversationPlan(page: Page, conversationId: string): Promise<SchedulePlan | null> {
  const conversation = await getJson<{
    runs: Array<{ artifacts: Array<{ artifact_type: string; artifact_id: string }> }>;
  }>(page, "/api/v1/chat/conversations/" + conversationId + "/");
  const planId = conversation.runs
    .flatMap((run) => run.artifacts)
    .filter((artifact) => artifact.artifact_type === "schedule_plan")
    .at(-1)?.artifact_id;
  return planId ? getJson<SchedulePlan>(page, "/api/v1/planning/plans/" + planId + "/") : null;
}

test("Agent-requested priority interaction opens across runs and saves a plan-only reorder", async ({ page }) => {
  test.setTimeout(12 * 60_000);
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

  const suffix = crypto.randomUUID();
  const titles = ["V3 staging Alpha " + suffix.slice(0, 8), "V3 staging Beta " + suffix.slice(0, 8)];
  const planDate = nextShanghaiWeekday();
  const dueAt = planDate + "T23:45";

  for (const title of titles) {
    await page.goto("/tasks");
    await page.getByRole("button", { name: "新建任务" }).click();
    await page.getByLabel("任务标题").fill(title);
    await page.getByLabel("项目").fill("Local V3 Agent interaction regression");
    await page.getByLabel("预计时长（分钟）").fill("20");
    await page.getByLabel(/截止时间 due_at/).fill(localInput(dueAt));
    await page.getByRole("button", { name: "创建任务" }).click();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  }

  const tasks = await getJson<TaskRecord[]>(page, "/api/v1/tasks/");
  const fixtureTasks = titles.map((title) => {
    const task = tasks.find((candidate) => candidate.title === title);
    expect(task, "UI-created fixture task " + title + " should be visible to the owner").toBeTruthy();
    return task as TaskRecord;
  });
  const originalPriorities = new Map(fixtureTasks.map((task) => [task.id, task.priority]));

  await page.goto("/chat");
  const composer = page.locator("#chat-message");
  const send = async (message: string) => {
    await expect(composer).toBeEnabled({ timeout: 240_000 });
    await composer.fill(message);
    await page.getByRole("button", { name: "发送消息" }).click();
  };

  await send("请先用任务列表按标题查找并确认这两条已有任务（不要把标题当作任务 ID），再只为「" + titles[0] + "」和「" + titles[1] + "」创建下一个工作日（" + planDate + "）的排程草案。暂时不要应用，也不要改任务的永久优先级。");
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]+$/);
  const conversationId = new URL(page.url()).pathname.split("/").at(-1) as string;
  await expect(page.getByRole("region", { name: "Agent 计划预览" })).toBeVisible({ timeout: 240_000 });
  await expect(composer).toBeEnabled({ timeout: 240_000 });
  await expect.poll(async () => (await latestConversationPlan(page, conversationId))?.id, { timeout: 180_000 })
    .toBeTruthy();
  const plan = await latestConversationPlan(page, conversationId);
  expect(plan?.status).toBe("draft");
  expect(new Set(orderedTaskIds(plan as SchedulePlan))).toEqual(new Set(fixtureTasks.map((task) => task.id)));

  await send("请为计划 " + (plan as SchedulePlan).id + " 打开本次计划的优先顺序交互，让我自己决定这两个任务的先后顺序。不要替我排序，不要更改永久优先级，也不要应用计划。");
  const ranker = page.getByRole("region", { name: "本次计划优先顺序" });
  await expect(ranker).toBeVisible({ timeout: 240_000 });
  await expect(page.getByRole("status").filter({ hasText: "助理已准备好" })).toBeVisible();
  await expect(composer).toBeEnabled({ timeout: 240_000 });

  await page.reload();
  const restoredRanker = page.getByRole("region", { name: "本次计划优先顺序" });
  await expect(restoredRanker).toBeVisible({ timeout: 60_000 });
  const planId = (plan as SchedulePlan).id;
  const beforeReorder = await getJson<SchedulePlan>(page, "/api/v1/planning/plans/" + planId + "/");
  const previousOrder = orderedTaskIds(beforeReorder);
  expect(previousOrder).toHaveLength(2);
  const taskToMove = previousOrder[1];
  const movingTitle = fixtureTasks.find((task) => task.id === taskToMove)?.title;
  expect(movingTitle).toBeTruthy();
  await restoredRanker.getByRole("button", { name: "上移：" + movingTitle }).click();
  await expect(restoredRanker.getByText("已更新本次计划顺序；任务的永久优先级没有更改。")).toBeVisible();
  const expectedOrder = [previousOrder[1], previousOrder[0]];
  await expect.poll(async () => orderedTaskIds(await getJson<SchedulePlan>(page, "/api/v1/planning/plans/" + planId + "/")))
    .toEqual(expectedOrder);

  const prioritiesAfter = await getJson<TaskRecord[]>(page, "/api/v1/tasks/");
  for (const task of fixtureTasks) {
    expect(prioritiesAfter.find((candidate) => candidate.id === task.id)?.priority)
      .toBe(originalPriorities.get(task.id));
  }

  await restoredRanker.getByRole("button", { name: "稍后再处理" }).click();
  await send("请为计划 " + planId + " 打开时间线交互控件，让我自己调整开始时间；不要替我修改时间，也不要应用计划。" );
  const timeline = page.getByRole("region", { name: "可编辑计划时间线" });
  await expect(timeline).toBeVisible({ timeout: 240_000 });
  await expect(page.getByRole("status").filter({ hasText: "助理已准备好“调整时间与时长”交互，现已打开。" })).toBeVisible();
  await expect(composer).toBeEnabled({ timeout: 240_000 });

  const beforePastEdit = await getJson<SchedulePlan>(page, "/api/v1/planning/plans/" + planId + "/");
  const tasksBeforePastEdit = await Promise.all(fixtureTasks.map((task) => getJson<TaskRecord>(page, "/api/v1/tasks/" + task.id + "/")));
  const todayBeforePastEdit = await getJson<TodaySummary>(page, "/api/v1/today/");
  const fixtureIds = new Set(fixtureTasks.map((task) => task.id));
  expect(tasksBeforePastEdit.every((task) => !task.planned_start_at && !task.planned_end_at)).toBe(true);
  expect(todayBeforePastEdit.planned_tasks.filter((task) => fixtureIds.has(task.id))).toEqual([]);
  const targetTask = fixtureTasks[0];
  const priorItem = beforePastEdit.items.find((item) => item.task_id === targetTask.id);
  expect(priorItem?.state).toBe("placed");
  const targetTaskCard = timeline.locator("ol > li").filter({ hasText: targetTask.title });
  await targetTaskCard.getByLabel("开始时间（Asia/Shanghai）").fill(localInput(new Date(Date.now() - 60 * 60_000).toISOString()));
  await targetTaskCard.getByRole("button", { name: "保存" }).click();
  await expect(timeline.getByRole("alert")).toContainText("不能把任务安排在过去");

  const afterPastEdit = await getJson<SchedulePlan>(page, "/api/v1/planning/plans/" + planId + "/");
  expect(afterPastEdit.version).toBe(beforePastEdit.version);
  expect(afterPastEdit.items.find((item) => item.task_id === targetTask.id)).toEqual(priorItem);
  const tasksAfterPastEdit = await Promise.all(fixtureTasks.map((task) => getJson<TaskRecord>(page, "/api/v1/tasks/" + task.id + "/")));
  expect(tasksAfterPastEdit.map((task) => [task.id, task.planned_start_at ?? null, task.planned_end_at ?? null]))
    .toEqual(tasksBeforePastEdit.map((task) => [task.id, task.planned_start_at ?? null, task.planned_end_at ?? null]));
  const todayAfterPastEdit = await getJson<TodaySummary>(page, "/api/v1/today/");
  expect(todayAfterPastEdit.planned_tasks.filter((task) => fixtureIds.has(task.id)))
    .toEqual(todayBeforePastEdit.planned_tasks.filter((task) => fixtureIds.has(task.id)));

  const pastDate = shanghaiDateOffset(-1);
  await send("请把计划 " + planId + " 中「" + targetTask.title + "」的开始时间精确改为 " + pastDate + " 10:00（Asia/Shanghai），保留原时长，只修改草案，不要应用。请如实说明修改是否成功。");
  await expect(composer).toBeEnabled({ timeout: 240_000 });
  const latestAssistantReply = page.getByRole("article").last();
  await expect(latestAssistantReply).toContainText(/过去|不能|无法|未能/);
  await expect(latestAssistantReply).not.toContainText(/已成功修改|已经改到/);

  const afterAgentPastEdit = await getJson<SchedulePlan>(page, "/api/v1/planning/plans/" + planId + "/");
  expect(afterAgentPastEdit.version).toBe(beforePastEdit.version);
  expect(afterAgentPastEdit.items.find((item) => item.task_id === targetTask.id)).toEqual(priorItem);
  const tasksAfterAgentPastEdit = await Promise.all(fixtureTasks.map((task) => getJson<TaskRecord>(page, "/api/v1/tasks/" + task.id + "/")));
  expect(tasksAfterAgentPastEdit.map((task) => [task.id, task.planned_start_at ?? null, task.planned_end_at ?? null]))
    .toEqual(tasksBeforePastEdit.map((task) => [task.id, task.planned_start_at ?? null, task.planned_end_at ?? null]));
  const todayAfterAgentPastEdit = await getJson<TodaySummary>(page, "/api/v1/today/");
  expect(todayAfterAgentPastEdit.planned_tasks.filter((task) => fixtureIds.has(task.id)))
    .toEqual(todayBeforePastEdit.planned_tasks.filter((task) => fixtureIds.has(task.id)));
});
