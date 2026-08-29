import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppSettingsPage } from "../src/pages/app-settings-page";
import { ONBOARDING_START_EVENT } from "../src/features/onboarding/storage";

const { downloadAndInstall } = vi.hoisted(() => ({ downloadAndInstall: vi.fn() }));
vi.mock("../src/platform", () => ({ isNativePlatform: () => true }));
vi.mock("../src/native/app-updater", () => ({
  getInstalledAppInfo: () => Promise.resolve({
    versionCode: 3,
    versionName: "1.0.2",
    canRequestPackageInstalls: true,
  }),
  openInstallPermissionSettings: vi.fn(),
  downloadAndInstall,
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AppSettingsPage />
    </QueryClientProvider>,
  );
}

describe("AppSettingsPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    downloadAndInstall.mockReset();
  });

  it("checks the signed release manifest and starts the native updater", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      enabled: true,
      release: {
        version_code: 4,
        version_name: "1.1.0",
        download_url: "https://steward.example.com/releases/timeagent.apk",
        sha256: "a".repeat(64),
        size_bytes: 1024,
        release_notes: "安全更新",
        published_at: "2026-08-07T00:00:00Z",
        minimum_supported_version_code: 3,
      },
    }))));
    downloadAndInstall.mockResolvedValue({ started: true });
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "检查更新" }));
    expect(await screen.findByText(/最新版本：1.1.0/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "下载并更新" }));
    expect(downloadAndInstall).toHaveBeenCalledWith(expect.objectContaining({
      expectedVersionCode: 4,
      expectedVersionName: "1.1.0",
      sha256: "a".repeat(64),
    }));
    expect(await screen.findByText(/已交给 Android 系统安装器/)).toBeInTheDocument();
  });

  it("allows the user to restart the onboarding tour", async () => {
    const listener = vi.fn();
    window.addEventListener(ONBOARDING_START_EVENT, listener);
    renderPage();

    await userEvent.click(screen.getByRole("button", { name: /重新查看新手引导/ }));

    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener(ONBOARDING_START_EVENT, listener);
  });
});
