import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AppLayout } from "../src/layouts/app-layout";

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
  it.each(["/calendar", "/tasks", "/reminders"])(
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
  });
});
