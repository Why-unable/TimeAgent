import { expect, test, type Page } from "@playwright/test";

const email = process.env.TIME_AGENT_E2E_EMAIL;
const password = process.env.TIME_AGENT_E2E_PASSWORD;
const enabled = process.env.TIME_AGENT_E2E_ENABLE_LIVE_AGENT === "1";

test.skip(
  !enabled || !email || !password,
  "Set the live-agent opt-in and dedicated test account credentials to run against the configured backend.",
);

type TaskRecord = {
  id: string;
  title: string;
  status: string;
  planned_start_at: string | null;
  planned_end_at: string | null;
};

type PlanItem = {
  task_id?: string;
  state?: string;
  start_at?: string;
  end_at?: string;
};

type SchedulePlan = {
  id: string;
  status: string;
  version: number;
  items: PlanItem[];
};

type TodaySummary = {
  date: string;
  timezone: string;
  events: Array<{ start_at: string; end_at: string }>;
  planned_tasks: TaskRecord[];
};

type UserPreferences = {
  timezone: string;
  workday_start: string;
  workday_end: string;
};

async function api<T>(page: Page, path: string, init: RequestInit = {}): Promise<T> {
  const response = await page.evaluate(async ({ requestPath, method, body }) => {
    const headers = new Headers({ Accept: "application/json" });
    if (body !== undefined) headers.set("Content-Type", "application/json");
    const csrf = document.cookie
      .split(";")
      .map((cookie) => cookie.trim())
      .find((cookie) => cookie.startsWith("csrftoken="))
      ?.slice("csrftoken=".length);
    if (csrf && !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase())) {
      headers.set("X-CSRFToken", decodeURIComponent(csrf));
    }
    const result = await fetch(requestPath, {
      method,
      credentials: "same-origin",
      headers,
      ...(body === undefined ? {} : { body }),
    });
    const text = await result.text();
    return {
      status: result.status,
      body: text ? JSON.parse(text) as unknown : undefined,
    };
  }, {
    requestPath: path,
    method: init.method ?? "GET",
    body: typeof init.body === "string" ? init.body : undefined,
  });
  if (response.status < 200 || response.status >= 300) {
    throw new Error(`API request failed (${response.status}): ${path}`);
  }
  return response.body as T;
}

function zonedParts(value: Date, timeZone = "Asia/Shanghai") {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(value);
  return Object.fromEntries(parts.map((part) => [part.type, part.value]));
}

function isoForShanghaiWallTime(date: string, minutes: number) {
  const hours = String(Math.floor(minutes / 60)).padStart(2, "0");
  const mins = String(minutes % 60).padStart(2, "0");
  return `${date}T${hours}:${mins}:00+08:00`;
}

function localInput(value: string) {
  const parts = zonedParts(new Date(value));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function tomorrowDate(date: string) {
  const [year, month, day] = date.split("-").map(Number);
  const tomorrow = new Date(Date.UTC(year, month - 1, day + 1));
  return `${tomorrow.getUTCFullYear()}-${String(tomorrow.getUTCMonth() + 1).padStart(2, "0")}-${String(tomorrow.getUTCDate()).padStart(2, "0")}`;
}

function minutesSinceMidnight(value: string) {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

function hasFreeWindow(
  busy: Array<{ start_at: string; end_at: string }>,
  start: string,
  end: string,
) {
  const startMs = Date.parse(start) - 10 * 60_000;
  const endMs = Date.parse(end) + 10 * 60_000;
  return busy.every((item) => (
    Date.parse(item.end_at) <= startMs || Date.parse(item.start_at) >= endMs
  ));
}

function itemForTask(plan: SchedulePlan, taskId: string) {
  return plan.items.find((item) => item.task_id === taskId && item.state === "placed");
}

async function readPlan(page: Page, conversationId: string) {
  const conversation = await api<{
    runs: Array<{ artifacts: Array<{ artifact_type: string; artifact_id: string }> }>;
  }>(page, `/api/v1/chat/conversations/${conversationId}/`);
  const planId = conversation.runs
    .flatMap((run) => run.artifacts)
    .filter((artifact) => artifact.artifact_type === "schedule_plan")
    .at(-1)?.artifact_id;
  if (!planId) return null;
  return api<SchedulePlan>(page, `/api/v1/planning/plans/${planId}/`);
}

test("real browser completes Agent plan edit, HITL apply, Task API and Today", async ({ page }) => {
  test.setTimeout(8 * 60_000);
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
    await expect(onboarding).toBeHidden();
  }

  const [today, preferences] = await Promise.all([
    api<TodaySummary>(page, "/api/v1/today/"),
    api<UserPreferences>(page, "/api/v1/preferences/me/"),
  ]);
  expect(today.timezone).toBe("Asia/Shanghai");
  expect(preferences.timezone).toBe(today.timezone);
  const nowParts = zonedParts(new Date());
  const nowMinutes = Number(nowParts.hour) * 60 + Number(nowParts.minute);
  const workdayStartMinutes = minutesSinceMidnight(preferences.workday_start);
  const workdayEndMinutes = minutesSinceMidnight(preferences.workday_end);
  const earliestStart = Math.max(
    workdayStartMinutes,
    Math.ceil((nowMinutes + 30) / 15) * 15,
  );
  const busy = [
    ...today.events,
    ...today.planned_tasks.flatMap((task) => task.planned_start_at && task.planned_end_at
      ? [{ start_at: task.planned_start_at, end_at: task.planned_end_at }]
      : []),
  ];
  let initialMinutes: number | undefined;
  for (let candidate = earliestStart; candidate + 45 <= workdayEndMinutes; candidate += 15) {
    const editMinutes = candidate + 15;
    const firstStart = isoForShanghaiWallTime(today.date, candidate);
    const firstEnd = isoForShanghaiWallTime(today.date, candidate + 30);
    const editStart = isoForShanghaiWallTime(today.date, editMinutes);
    const editEnd = isoForShanghaiWallTime(today.date, editMinutes + 30);
    if (
      hasFreeWindow(busy, firstStart, firstEnd)
      && hasFreeWindow(busy, editStart, editEnd)
    ) {
      initialMinutes = candidate;
      break;
    }
  }
  expect(
    initialMinutes,
    "No pair of future conflict-free 30-minute work windows fits the configured workday today.",
  ).toBeDefined();

  const initialStart = isoForShanghaiWallTime(today.date, initialMinutes as number);
  const initialEnd = isoForShanghaiWallTime(today.date, (initialMinutes as number) + 30);
  const editedMinutes = (initialMinutes as number) + 60;
  const editedStart = isoForShanghaiWallTime(today.date, editedMinutes);
  const editedEnd = isoForShanghaiWallTime(today.date, editedMinutes + 30);
  const title = "E2E-LIVE-AgentUX-V2-acceptance";
  let taskId: string | undefined;

  try {
    const existingAcceptanceTask = (await api<TaskRecord[]>(page, "/api/v1/tasks/")).find(
      (task) => task.title.startsWith("E2E-LIVE-") && task.status === "pending",
    );
    if (existingAcceptanceTask) {
      taskId = existingAcceptanceTask.id;
      await api(page, `/api/v1/tasks/${taskId}/`, {
        method: "PATCH",
        body: JSON.stringify({
          title,
          project: "Live Agent browser acceptance",
          estimated_minutes: 30,
          due_at: `${tomorrowDate(today.date)}T23:45:00+08:00`,
          planned_start_at: null,
          planned_end_at: null,
        }),
      });
    } else {
      await page.goto("/tasks");
      await page.getByRole("button", { name: "新建任务" }).click();
      await page.getByLabel("任务标题").fill(title);
      await page.getByLabel("项目").fill("Live Agent browser acceptance");
      await page.getByLabel("预计时长（分钟）").fill("30");
      await page.getByLabel(/截止时间 due_at/).fill(
        localInput(`${tomorrowDate(today.date)}T23:45:00+08:00`),
      );
      await page.getByRole("button", { name: "创建任务" }).click();
      await expect(page.getByRole("heading", { name: title })).toBeVisible();

      const tasks = await api<TaskRecord[]>(page, "/api/v1/tasks/");
      taskId = tasks.find((task) => task.title === title)?.id;
    }
    expect(taskId).toBeTruthy();

    await page.goto("/chat");
    const composer = page.locator("#chat-message");
    const send = async (message: string) => {
      await expect(composer).toBeEnabled({ timeout: 240_000 });
      await composer.fill(message);
      await page.getByRole("button", { name: "发送消息" }).click();
    };
    const exactInitial = `${today.date} ${String(initialMinutes! / 60 | 0).padStart(2, "0")}:${String(initialMinutes! % 60).padStart(2, "0")}`;
    await send(`请只为任务「${title}」创建今天的 30 分钟排程草案，精确安排在 ${exactInitial}（Asia/Shanghai）。这是明确时间要求；不要应用，也不要调整其他任务。`);
    await expect(page).toHaveURL(/\/chat\/[0-9a-f-]+$/);
    const planCard = page.getByRole("region", { name: "Agent 计划预览" });
    await expect(planCard).toBeVisible({ timeout: 240_000 });
    const conversationId = new URL(page.url()).pathname.split("/").at(-1) as string;
    await expect.poll(async () => (await readPlan(page, conversationId))?.id, { timeout: 180_000 }).toBeTruthy();
    let plan = await readPlan(page, conversationId);
    expect(plan).toBeTruthy();
    let planItem = itemForTask(plan as SchedulePlan, taskId as string);
    expect(planItem?.start_at).toBeTruthy();
    expect(Date.parse(planItem!.start_at as string)).toBe(Date.parse(initialStart));
    expect(Date.parse(planItem!.end_at as string)).toBe(Date.parse(initialEnd));

    const planId = (plan as SchedulePlan).id;
    const firstVersion = (plan as SchedulePlan).version;
    const exactEdited = `${today.date} ${String(editedMinutes / 60 | 0).padStart(2, "0")}:${String(editedMinutes % 60).padStart(2, "0")}`;
    await send(`请将计划 ${planId} 中的「${title}」精确改到今天 ${exactEdited}（Asia/Shanghai），时长仍为 30 分钟，只保留草案，不要应用。`);
    await expect.poll(async () => (await api<SchedulePlan>(page, `/api/v1/planning/plans/${planId}/`)).version, { timeout: 240_000 })
      .toBeGreaterThan(firstVersion);
    await expect(composer).toBeEnabled({ timeout: 240_000 });
    plan = await api<SchedulePlan>(page, `/api/v1/planning/plans/${planId}/`);
    planItem = itemForTask(plan, taskId as string);
    expect(Date.parse(planItem?.start_at ?? "")).toBe(Date.parse(editedStart));
    expect(Date.parse(planItem?.end_at ?? "")).toBe(Date.parse(editedEnd));

    await send(`请应用计划 ${planId} 当前版本 ${plan.version}。它只包含测试任务「${title}」；请先提交正式审批，不要绕过确认流程。`);
    const approval = page.locator("article").filter({ hasText: "需要你确认" }).last();
    await expect(approval).toBeVisible({ timeout: 240_000 });
    await expect(approval.getByRole("button", { name: "确认并应用" })).toBeEnabled();
    await approval.getByRole("button", { name: "确认并应用" }).click();

    await expect.poll(async () => {
      const proposals = await api<Array<{ conversation_id: string; status: string }>>(
        page,
        "/api/v1/action-proposals/",
      );
      return proposals.find((proposal) => proposal.conversation_id === conversationId)?.status;
    }, { timeout: 240_000 }).toBe("executed");
    await expect.poll(async () => (await api<SchedulePlan>(page, `/api/v1/planning/plans/${planId}/`)).status, { timeout: 240_000 })
      .toBe("applied");

    const appliedTask = (await api<TaskRecord[]>(page, "/api/v1/tasks/")).find((task) => task.id === taskId);
    expect(appliedTask?.planned_start_at).toBeTruthy();
    expect(Date.parse(appliedTask!.planned_start_at as string)).toBe(Date.parse(editedStart));
    expect(Date.parse(appliedTask!.planned_end_at as string)).toBe(Date.parse(editedEnd));

    await page.goto("/today");
    await expect(page.getByText(title, { exact: true })).toBeVisible();
    const todayAfterApply = await api<TodaySummary>(page, "/api/v1/today/");
    const todayTask = todayAfterApply.planned_tasks.find((task) => task.id === taskId);
    expect(todayAfterApply.timezone).toBe("Asia/Shanghai");
    expect(Date.parse(todayTask?.planned_start_at ?? "")).toBe(Date.parse(editedStart));
    expect(Date.parse(todayTask?.planned_end_at ?? "")).toBe(Date.parse(editedEnd));
  } finally {
    if (taskId) {
      await api(page, `/api/v1/tasks/${taskId}/`, {
        method: "PATCH",
        body: JSON.stringify({ planned_start_at: null, planned_end_at: null }),
      }).catch(() => undefined);
    }
  }
});
