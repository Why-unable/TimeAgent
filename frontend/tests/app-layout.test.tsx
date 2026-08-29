import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppLayout } from "../src/layouts/app-layout";
import { ONBOARDING_START_EVENT } from "../src/features/onboarding/storage";

const getLatestAndroidReleaseMock = vi.hoisted(() => vi.fn());

vi.mock("../src/api/app-updates", () => ({
  getLatestAndroidRelease: getLatestAndroidReleaseMock,
}));

beforeEach(() => {
  getLatestAndroidReleaseMock.mockResolvedValue({
    enabled: true,
    release: {
      version_code: 12,
      version_name: "1.1.8",
      download_url: "https://steward.example.test/releases/timeagent-1.1.8.apk",
      sha256: "a".repeat(64),
      size_bytes: 4_194_304,
      release_notes: "测试版本",
      published_at: "2026-08-27T00:00:00Z",
      minimum_supported_version_code: 1,
    },
  });
});

vi.mock("../src/features/accounts/hooks", () => ({
  useCurrentUser: () => ({
    data: {
      id: 1,
      email: "desktop@example.test",
      display_name: "桌面用户",
      is_staff: false,
    },
  }),
}));

vi.mock("../src/features/preferences/hooks", () => ({
  useCurrentUserPreference: () => ({ data: { timezone: "Asia/Shanghai" } }),
}));

function renderLayout(pathname: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="*" element={<p>页面内容</p>} />
          </Route>
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("AppLayout desktop navigation", () => {
  it.each(["/calendar", "/tasks", "/planning", "/reminders"])(
    "uses one aggregated 日程 entry for %s",
    (pathname) => {
      renderLayout(pathname);
      const sidebar = screen.getByTestId("desktop-sidebar");
      const scheduleLinks = within(sidebar).getAllByRole("link", { name: /日程/ });

      expect(scheduleLinks).toHaveLength(1);
      expect(scheduleLinks[0]).toHaveAttribute("href", "/calendar");
      expect(scheduleLinks[0]).toHaveAttribute("aria-current", "page");
      expect(within(sidebar).queryByRole("link", { name: /^任务/ })).not.toBeInTheDocument();
      expect(within(sidebar).queryByRole("link", { name: /^提醒/ })).not.toBeInTheDocument();
    },
  );

  it("keeps system diagnostics hidden for non-staff users", () => {
    renderLayout("/today");
    const sidebar = screen.getByTestId("desktop-sidebar");

    expect(within(sidebar).getByText("桌面用户")).toBeInTheDocument();
    expect(within(sidebar).queryByRole("link", { name: /系统状态/ })).not.toBeInTheDocument();
    expect(within(sidebar).getByRole("link", { name: /应用设置/ })).toHaveAttribute(
      "href",
      "/settings/app",
    );
  });

  it("starts the onboarding tour from the workspace brand", async () => {
    const listener = vi.fn();
    window.addEventListener(ONBOARDING_START_EVENT, listener);
    renderLayout("/today");

    await userEvent.click(screen.getByRole("button", { name: "开始使用指引" }));

    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener(ONBOARDING_START_EVENT, listener);
  });

  it("offers the latest Android release through QR and direct download", async () => {
    renderLayout("/today");

    await userEvent.click(screen.getByRole("button", { name: "下载手机 App" }));

    const dialog = await screen.findByRole("dialog", { name: "下载 Time Agent" });
    expect(within(dialog).getByText("Time Agent 1.1.8")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("手机扫码下载")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "直接下载 APK" })).toHaveAttribute(
      "href",
      "https://steward.example.test/releases/timeagent-1.1.8.apk",
    );

    await userEvent.click(within(dialog).getByRole("button", { name: "关闭下载窗口" }));
    expect(screen.queryByRole("dialog", { name: "下载 Time Agent" })).not.toBeInTheDocument();
  });
});
