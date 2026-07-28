import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { MobileNavigation } from "../src/layouts/mobile-navigation";

vi.mock("../src/features/accounts/hooks", () => ({
  useCurrentUser: () => ({ data: { id: 1, is_staff: false } }),
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
  it("renders exactly four bottom tabs with no independent 日历 entry", () => {
    renderNav("/today");
    const nav = screen.getByRole("navigation", { name: "移动端主导航" });
    const primaryLinks = nav.querySelectorAll("a");
    expect(primaryLinks).toHaveLength(3);
    expect(screen.getByRole("button", { name: "更多" })).toBeInTheDocument();
    expect(screen.getByText("今天")).toBeInTheDocument();
    expect(screen.getByText("聊天")).toBeInTheDocument();
    expect(screen.getByText("日程")).toBeInTheDocument();
    expect(screen.queryByText("日历")).not.toBeInTheDocument();
  });

  it.each(["/calendar", "/tasks", "/reminders"])(
    "highlights the 日程 tab on %s",
    (path) => {
      renderNav(path);
      const scheduleLink = screen.getByText("日程").closest("a");
      expect(scheduleLink).not.toBeNull();
      expect(scheduleLink).toHaveAttribute("aria-current", "page");
      // 今天 should not be highlighted
      const todayLink = screen.getByText("今天").closest("a");
      expect(todayLink).not.toHaveAttribute("aria-current", "page");
    },
  );

  it("marks 今天 active on /today and not others", () => {
    renderNav("/today");
    const todayLink = screen.getByText("今天").closest("a");
    expect(todayLink).toHaveAttribute("aria-current", "page");
    const scheduleLink = screen.getByText("日程").closest("a");
    expect(scheduleLink).not.toHaveAttribute("aria-current", "page");
  });
});
