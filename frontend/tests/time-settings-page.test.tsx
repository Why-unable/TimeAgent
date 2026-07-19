import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TimeSettingsPage } from "../src/pages/time-settings-page";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TimeSettingsPage />
    </QueryClientProvider>,
  );
}

const preference = {
  timezone: "Asia/Shanghai",
  locale: "zh-CN",
  workday_start: "09:00:00",
  workday_end: "18:00:00",
  sleep_start: "23:00:00",
  sleep_end: "07:00:00",
  default_event_duration_minutes: 60,
  preferred_focus_periods: [],
  default_reminder_offsets: [],
  weather_location: "",
  news_topics: [],
  briefing_time: "08:00:00",
  planning_rules: {},
  updated_at: "2026-07-19T00:00:00Z",
};

describe("TimeSettingsPage external data preferences", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("saves weather location and normalized news topics and shows trusted feeds", async () => {
    let patchBody: Record<string, unknown> | undefined;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/preferences/me/") && (init?.method ?? "GET") === "GET") {
        return new Response(JSON.stringify(preference));
      }
      if (url.endsWith("/api/v1/preferences/me/") && init?.method === "PATCH") {
        patchBody = JSON.parse(String(init.body));
        return new Response(JSON.stringify({ ...preference, ...patchBody }));
      }
      if (url.endsWith("/api/v1/providers/catalog/")) {
        return new Response(JSON.stringify({
          weather_provider: "open_meteo",
          news_provider: "rss",
          news_feeds: [{
            name: "OpenAI News",
            publisher: "OpenAI",
            url: "https://openai.com/news/rss.xml",
            topics: ["artificial intelligence", "openai"],
          }],
          topic_aliases: {},
        }));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderPage();
    await userEvent.type(await screen.findByPlaceholderText("上海 / London / 10001"), "上海");
    await userEvent.type(
      screen.getByPlaceholderText("人工智能, OpenAI, GitHub, Python"),
      "人工智能，OpenAI\nPython",
    );
    await userEvent.click(screen.getByRole("button", { name: "保存偏好" }));

    expect(patchBody).toEqual(expect.objectContaining({
      weather_location: "上海",
      news_topics: ["人工智能", "OpenAI", "Python"],
    }));
    await userEvent.click(screen.getByRole("button", { name: "查看当前新闻来源" }));
    expect(await screen.findByRole("link", { name: /OpenAI News/ })).toHaveAttribute(
      "href",
      "https://openai.com/news/rss.xml",
    );
  });
});
