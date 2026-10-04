import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { MobileNavigation } from "../src/layouts/mobile-navigation";

vi.mock("../src/features/accounts/hooks", () => ({
  useCurrentUser: () => ({ data: { id: 1, is_staff: false } }),
}));
vi.mock("../src/platform", () => ({ isNativePlatform: () => true }));
vi.mock("@capacitor/app", () => ({
  App: { addListener: vi.fn(async () => ({ remove: vi.fn(async () => undefined) })) },
}));

function renderNav(initialEntry: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <QueryClientProvider client={client}>
        <MobileNavigation />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("MobileNavigation", () => {
  it("renders the four stable Today, Assistant, Plan, and Me destinations", () => {
    renderNav("/today");
    const nav = screen.getByRole("navigation", { name: "移动端主导航" });
    const primaryLinks = nav.querySelectorAll("a");
    expect(primaryLinks).toHaveLength(3);
    expect(screen.getByRole("button", { name: "我的" })).toBeInTheDocument();
    expect(screen.getByText("今天")).toBeInTheDocument();
    expect(screen.getByText("助理")).toBeInTheDocument();
    expect(screen.getByText("计划")).toBeInTheDocument();
    expect(screen.queryByText("日历")).not.toBeInTheDocument();
  });

  it.each(["/schedule", "/calendar", "/tasks", "/planning"])(
    "highlights 计划 for plan routes on %s",
    (path) => {
      renderNav(path);
      const planLink = screen.getByText("计划").closest("a");
      expect(planLink).not.toBeNull();
      expect(planLink).toHaveAttribute("aria-current", "page");
      // 今天 should not be highlighted
      const todayLink = screen.getByText("今天").closest("a");
      expect(todayLink).not.toHaveAttribute("aria-current", "page");
    },
  );

  it("marks reminders as part of Me instead of Plan", () => {
    renderNav("/reminders");
    expect(screen.getByRole("button", { name: /我的/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("计划").closest("a")).not.toHaveAttribute("aria-current", "page");
  });

  it("marks 今天 active on /today and not others", () => {
    renderNav("/today");
    const todayLink = screen.getByText("今天").closest("a");
    expect(todayLink).toHaveAttribute("aria-current", "page");
    const planLink = screen.getByText("计划").closest("a");
    expect(planLink).not.toHaveAttribute("aria-current", "page");
  });

  it("marks 助理 active on chat routes", () => {
    renderNav("/chat/123");
    expect(screen.getByText("助理").closest("a")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("计划").closest("a")).not.toHaveAttribute("aria-current", "page");
  });

  it("exposes grouped low-frequency destinations from the Me drawer", async () => {
    renderNav("/today");
    await userEvent.click(screen.getByRole("button", { name: "我的" }));
    expect(screen.getByRole("dialog", { name: "我的" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "我的功能" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /提醒/ })).toHaveAttribute("href", "/reminders");
    expect(screen.getByRole("link", { name: /简报/ })).toHaveAttribute("href", "/briefings");
    expect(screen.getByRole("heading", { name: "时间服务" })).toBeInTheDocument();
    expect(screen.queryByText(/Web Push/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /应用设置/ })).toHaveAttribute(
      "href",
      "/settings/app",
    );
  });

  it("closes the Me drawer when browser navigation changes route", async () => {
    function NavigationHarness() {
      const navigate = useNavigate();
      return <><button type="button" onClick={() => navigate("/settings/account")}>切换路由</button><MobileNavigation /></>;
    }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/today"]}>
        <QueryClientProvider client={client}><NavigationHarness /></QueryClientProvider>
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "我的" }));
    expect(screen.getByRole("dialog", { name: "我的" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "切换路由" }));
    expect(screen.queryByRole("dialog", { name: "我的" })).not.toBeInTheDocument();
  });
});
