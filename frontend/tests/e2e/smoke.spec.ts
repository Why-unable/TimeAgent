import { expect, test } from "@playwright/test";

test("renders the system status shell", async ({ page }) => {
  await page.route("**/health/ready", async (route) => {
    await route.fulfill({
      json: { status: "ready", checks: { database: "ok", redis: "ok" } },
    });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "系统状态" })).toBeVisible();
});

