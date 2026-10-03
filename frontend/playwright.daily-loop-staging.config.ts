import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: /live-daily-loop-staging\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  timeout: 6 * 60_000,
  expect: { timeout: 30_000 },
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:7081",
    timezoneId: "Asia/Shanghai",
    actionTimeout: 15_000,
    trace: "retain-on-failure",
    video: "off",
    screenshot: "only-on-failure",
  },
});
