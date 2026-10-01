import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.TIME_AGENT_E2E_BASE_URL ?? "https://steward.uresofa.me";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "live-agent.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 8 * 60_000,
  expect: { timeout: 30_000 },
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    timezoneId: "Asia/Shanghai",
    actionTimeout: 15_000,
    trace: "off",
    video: "off",
    screenshot: "off",
  },
});
