import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingTour } from "../src/components/onboarding/onboarding-tour";
import {
  hasCompletedOnboarding,
  markOnboardingCompleted,
} from "../src/features/onboarding/storage";

function visibleRect(): DOMRect {
  return {
    x: 20,
    y: 20,
    top: 20,
    right: 140,
    bottom: 76,
    left: 20,
    width: 120,
    height: 56,
    toJSON: () => ({}),
  } as DOMRect;
}

function TourHarness() {
  const [moreOpen, setMoreOpen] = useState(false);
  return (
    <>
      <button type="button" data-onboarding-id="nav-today">今天入口</button>
      <button type="button" data-onboarding-id="nav-chat">聊天入口</button>
      <button type="button" data-onboarding-id="nav-schedule">日程入口</button>
      <button type="button" data-onboarding-id="nav-more" onClick={() => setMoreOpen(true)}>更多入口</button>
      {moreOpen && <button type="button" data-onboarding-id="nav-time-settings">偏好设置入口</button>}
      <OnboardingTour userId={7} />
    </>
  );
}

describe("OnboardingTour", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(visibleRect);
  });

  it("walks a first-time user through visible navigation and persists completion", async () => {
    render(<MemoryRouter><TourHarness /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "欢迎使用 Time Agent" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /开始探索/ }));
    expect(await screen.findByRole("heading", { name: "从“今天”开始" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /打开“今天”/ }));
    await userEvent.click(await screen.findByRole("button", { name: /打开“聊天”/ }));
    await userEvent.click(await screen.findByRole("button", { name: /打开“日程”/ }));
    await userEvent.click(await screen.findByRole("button", { name: /打开“更多”/ }));
    await userEvent.click(await screen.findByRole("button", { name: /打开“偏好设置”/ }));

    expect(await screen.findByRole("heading", { name: "主要功能已经认识完了" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /完成引导/ }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(hasCompletedOnboarding(7)).toBe(true);
  });

  it("does not reopen automatically after the current guide version is completed", () => {
    markOnboardingCompleted(7);
    render(<MemoryRouter><TourHarness /></MemoryRouter>);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
