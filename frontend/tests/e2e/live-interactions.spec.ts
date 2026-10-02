import { expect, test, type Page } from "@playwright/test";

const email = process.env.TIME_AGENT_E2E_EMAIL;
const password = process.env.TIME_AGENT_E2E_PASSWORD;
const enabled = process.env.TIME_AGENT_E2E_ENABLE_INTERACTIONS === "1";
const allowedBaseUrl = "http://127.0.0.1:7081";

test.skip(
  !enabled || !email || !password || process.env.TIME_AGENT_E2E_BASE_URL !== allowedBaseUrl,
  "This live interaction regression is restricted to the local V3 staging service on 127.0.0.1:7081.",
);

type ApiResult<T> = { status: number; data: T };
type TaskRecord = { id: string; title: string; status: string };
type PlanRecord = { id: string; version: number };

async function api<T>(page: Page, path: string, method = "GET", body?: unknown): Promise<ApiResult<T>> {
  return page.evaluate(async ({ path, method, body }) => {
    const csrf = document.cookie
      .split(";")
      .map((entry) => entry.trim())
      .find((entry) => entry.startsWith("csrftoken="))
      ?.slice("csrftoken=".length);
    const headers = new Headers({ Accept: "application/json" });
    if (body !== undefined) headers.set("Content-Type", "application/json");
    if (csrf && !["GET", "HEAD", "OPTIONS"].includes(method)) {
      headers.set("X-CSRFToken", decodeURIComponent(csrf));
    }
    const response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    return { status: response.status, data: await response.json() as T };
  }, { path, method, body });
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
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
}

test("local staging opens timeline editing and restores completion feedback after reload", async ({ page }) => {
  test.setTimeout(90_000);
  await page.addInitScript(() => {
    window.localStorage.setItem("time-agent:onboarding:1:v1", "completed");
  });
  await page.goto("/login");
  await page.getByLabel("邮箱").fill(email as string);
  await page.getByLabel("密码").fill(password as string);
  await page.getByRole("button", { name: "登录", exact: true }).last().click();
  await expect(page).toHaveURL(/\/today$/);
  await page.waitForTimeout(1_000);
  const skipOnboarding = page.getByRole("button", { name: "暂时跳过" });
  if (await skipOnboarding.isVisible().catch(() => false)) await skipOnboarding.click();

  const date = shanghaiDateOffset(0);
  const planDate = shanghaiDateOffset(2);
  const timelineTitle = `V3-LIVE-TIMELINE-${crypto.randomUUID()}`;
  const completionTitle = `V3-LIVE-COMPLETION-${crypto.randomUUID()}`;
  const timelineTask = await api<TaskRecord>(page, "/api/v1/tasks/", "POST", {
    title: timelineTitle,
    project: "Local V3 interaction regression",
    estimated_minutes: 30,
    due_at: `${shanghaiDateOffset(5)}T23:45:00+08:00`,
  });
  const completionTask = await api<TaskRecord>(page, "/api/v1/tasks/", "POST", {
    title: completionTitle,
    project: "Local V3 interaction regression",
    estimated_minutes: 30,
    due_at: `${date}T23:45:00+08:00`,
  });
  expect(timelineTask.status).toBe(201);
  expect(completionTask.status).toBe(201);

  const activeTasks = ((await api<TaskRecord[]>(page, "/api/v1/tasks/")).data)
    .filter((task) => task.status === "pending" || task.status === "in_progress");
  await page.goto("/planning");
  await page.getByRole("button", { name: "高级规划设置" }).click();
  const taskSelection = page.getByRole("heading", { name: "安排哪些任务" }).locator("xpath=ancestor::section[1]");
  const taskCheckboxes = taskSelection.getByRole("checkbox");
  await expect(taskCheckboxes).toHaveCount(activeTasks.length);
  for (let index = 0; index < activeTasks.length; index += 1) {
    const checkbox = taskCheckboxes.nth(index);
    if (activeTasks[index].id === timelineTask.data.id) await checkbox.check();
    else await checkbox.uncheck();
  }
  await page.getByLabel(/开始（Asia\/Shanghai）/).fill(`${planDate}T09:00`);
  await page.getByLabel(/结束（Asia\/Shanghai）/).fill(`${planDate}T17:00`);
  const planResponsePromise = page.waitForResponse((response) => (
    new URL(response.url()).pathname === "/api/v1/planning/plans/"
    && response.request().method() === "POST"
  ));
  await page.getByRole("button", { name: "生成草案" }).click();
  const planResponse = await planResponsePromise;
  expect(planResponse.status()).toBe(201);
  const plan = await planResponse.json() as PlanRecord;
  await page.getByRole("button", { name: "调整时间与时长" }).click();
  await expect(page.getByRole("region", { name: "可编辑计划时间线" })).toBeVisible();

  await page.goto("/today");
  const completeButton = page.getByRole("button", { name: `完成任务：${completionTitle}` });
  await expect(completeButton).toBeVisible();
  await completeButton.click();
  const feedback = page.getByRole("region", { name: "任务完成反馈" });
  await expect(feedback).toBeVisible();
  await expect(feedback.getByRole("heading", { name: completionTitle })).toBeVisible();
  await page.reload();
  const restoredFeedback = page.getByRole("region", { name: "任务完成反馈" });
  await expect(restoredFeedback).toBeVisible();
  await expect(restoredFeedback.getByRole("heading", { name: completionTitle })).toBeVisible();
  const pending = await api<Array<{ type: string; task_id: string }>>(
    page,
    `/api/v1/interactions/?type=task_completion&task_id=${completionTask.data.id}`,
  );
  expect(pending.status).toBe(200);
  expect(pending.data).toHaveLength(1);
  expect(pending.data[0].task_id).toBe(completionTask.data.id);
  expect(plan.id).toBeTruthy();
});
