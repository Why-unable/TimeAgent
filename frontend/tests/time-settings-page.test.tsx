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
  weather_forecast_days: 3,
  news_topics: [],
  briefing_time: "08:00:00",
  planning_rules: {},
  updated_at: "2026-07-19T00:00:00Z",
};

describe("TimeSettingsPage external data preferences", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("requires a catalog city selection and saves only trusted news topics", async () => {
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
          news_topics: ["openai", "artificial intelligence"],
          timezones: ["Asia/Shanghai"],
          locales: ["zh-CN", "en-US"],
        }));
      }
      if (url.includes("/api/v1/providers/locations/")) {
        return new Response(JSON.stringify([{ name: "合肥", admin1: "安徽", country: "中国", timezone: "Asia/Shanghai", label: "合肥 / 安徽 / 中国" }]));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderPage();
    await userEvent.type(await screen.findByPlaceholderText("输入城市，如合肥"), "合肥");
    await userEvent.click(await screen.findByRole("button", { name: /合肥/ }));
    await userEvent.click(await screen.findByText("openai", { selector: "button" }));
    await userEvent.click(screen.getByRole("button", { name: "保存偏好" }));

    expect(patchBody).toEqual(expect.objectContaining({
      weather_location: "合肥 / 安徽 / 中国",
      news_topics: ["openai"],
    }));
    expect(await screen.findByRole("link", { name: /OpenAI News/ })).toHaveAttribute(
      "href",
      "https://openai.com/news/rss.xml",
    );
  });
});
