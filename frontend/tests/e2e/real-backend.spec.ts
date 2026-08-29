import { expect, test } from "@playwright/test";

const email = process.env.TIME_AGENT_E2E_EMAIL;
const password = process.env.TIME_AGENT_E2E_PASSWORD;

test.skip(
  !email || !password,
  "Set TIME_AGENT_E2E_EMAIL and TIME_AGENT_E2E_PASSWORD for an isolated real-backend run.",
);

function localInput(iso: string) {
  const value = new Date(iso);
  return new Date(value.getTime() - value.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}

test("runs the Phase A-E write path against a real backend", async ({ page }) => {
  test.setTimeout(90_000);
  const title = `Phase A-E validation ${Date.now()}`;
  await page.addInitScript(() => {
    window.localStorage.setItem("time-agent:onboarding:1:v1", "completed");
  });

  await page.goto("/login");
  await page.getByLabel("邮箱").fill(email as string);
  await page.getByLabel("密码").fill(password as string);
  await page.getByRole("button", { name: "登录", exact: true }).last().click();
  await expect(page).toHaveURL(/\/today$/);

  await page.goto("/tasks");
  await page.getByRole("button", { name: "新建任务" }).click();
  await page.getByLabel("任务标题").fill(title);
  await page.getByLabel("项目").fill("Phase validation");
  await page.getByLabel("预计时长（分钟）").fill("45");
  await page.getByLabel(/截止时间 due_at/).fill(
    localInput(new Date(Date.now() + 24 * 60 * 60_000).toISOString()),
  );
  await page.getByRole("button", { name: "创建任务" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();

  await page.getByRole("button", { name: `开始任务：${title}` }).click();
  await page.getByRole("button", { name: "进行中", exact: true }).click();
  await expect(page.getByRole("button", { name: `暂停任务：${title}` })).toBeVisible();
  await page.getByRole("button", { name: `查看执行摘要：${title}` }).click();
  await expect(page.getByText("已记录 1 次动作")).toBeVisible();

  await page.getByRole("button", { name: `查看估时建议：${title}` }).click();
  await expect(page.getByText(/建议预留 \d+ 分钟/)).toBeVisible();
  await page.getByRole("button", { name: "太短" }).click();
  await expect(page.getByText("估时反馈已记录。", { exact: true })).toBeVisible();

  await page.goto("/planning");
  await page.getByRole("checkbox", { name: new RegExp(title) }).click();
  await page.getByRole("button", { name: "生成草案" }).click();
  await expect(page.getByText("已安排", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "确认应用" }).click();
  await expect(page.getByText("计划已应用。", { exact: true })).toBeVisible();

  const plannedTask = await page.evaluate(async (taskTitle) => {
    const response = await fetch("/api/v1/tasks/");
    if (!response.ok) throw new Error(`Task fetch failed: ${response.status}`);
    const tasks = (await response.json()) as Array<{
      title: string;
      planned_start_at: string | null;
      planned_end_at: string | null;
    }>;
    return tasks.find((task) => task.title === taskTitle);
  }, title);
  expect(plannedTask?.planned_start_at).toBeTruthy();
  expect(plannedTask?.planned_end_at).toBeTruthy();

  await page.goto("/today");
  const insight = page.locator("article").filter({
    hasText: title,
    has: page.getByRole("button", { name: "关闭此类洞察" }),
  });
  await expect(insight).toBeVisible();
  await insight.getByRole("button", { name: "关闭此类洞察" }).click();
  await expect(insight).toBeHidden();

  await page.goto("/planning");
  await page.getByRole("tab", { name: "局部调整" }).click();
  await page.getByRole("checkbox", { name: new RegExp(title) }).click();
  await page.getByRole("button", { name: "为已选任务创建免审批策略" }).click();
  await page.getByRole("combobox").selectOption({ label: "柔性任务局部调整" });
  await page.getByLabel("阻塞开始").fill(localInput(plannedTask?.planned_start_at as string));
  await page.getByLabel("阻塞结束").fill(localInput(plannedTask?.planned_end_at as string));
  await page.getByRole("button", { name: "预览局部调整" }).click();
  await expect(page.getByText(/移动 1 项/)).toBeVisible();
  await page.getByRole("button", { name: "执行这次调整" }).click();
  await expect(page.getByText("变更批次已应用")).toBeVisible();
  await page.getByRole("button", { name: "撤销" }).click();
  await expect(page.getByText("已恢复调整前安排。", { exact: true })).toBeVisible();
});
