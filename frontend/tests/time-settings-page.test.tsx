import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TimeSettingsPage } from "../src/pages/time-settings-page";

vi.mock("../src/native/geolocation", () => ({
  getCurrentDeviceCoordinates: vi.fn(async () => ({ latitude: 22.27, longitude: 113.57 })),
}));

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
  weather_location_data: {},
  weather_forecast_days: 3,
  require_event_creation_approval: false,
  require_event_cancellation_approval: false,
  news_topics: [],
  briefing_time: "08:00:00",
  planning_rules: {},
  updated_at: "2026-07-19T00:00:00Z",
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={client}><TimeSettingsPage /></QueryClientProvider></MemoryRouter>);
}

describe("TimeSettingsPage external data preferences", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses the server administrative catalog and saves only a resolved location", async () => {
    let patchBody: Record<string, unknown> | undefined;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/preferences/me/") && (init?.method ?? "GET") === "GET") return new Response(JSON.stringify(preference));
      if (url.endsWith("/api/v1/preferences/me/") && init?.method === "PATCH") {
        patchBody = JSON.parse(String(init.body));
        return new Response(JSON.stringify({ ...preference, ...patchBody }));
      }
      if (url.endsWith("/api/v1/providers/catalog/")) return new Response(JSON.stringify({ weather_provider: "open_meteo", news_provider: "rss", news_feeds: [], topic_aliases: {}, news_topics: ["openai"], timezones: ["Asia/Shanghai"], locales: ["zh-CN", "en-US"] }));
      if (url.endsWith("/api/v1/providers/locations/administrative-areas/")) return new Response(JSON.stringify([{ code: "440000", name: "广东省" }]));
      if (url.includes("administrative-areas/?province_code=440000")) return new Response(JSON.stringify([{ code: "440400", name: "珠海市" }]));
      if (url.includes("administrative-areas/?city_code=440400")) return new Response(JSON.stringify([{ code: "440402", name: "香洲区" }]));
      if (url.includes("locations/resolve/")) return new Response(JSON.stringify({ provider: "open_meteo", provider_location_id: "1", name: "香洲区", admin1: "广东省", country: "中国", timezone: "Asia/Shanghai", label: "广东省 / 珠海市 / 香洲区", latitude: 22.27, longitude: 113.57, province: "广东省", city: "珠海市", district: "香洲区" }));
      throw new Error(`Unexpected request: ${url}`);
    }));

    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("option", { name: "广东省" });
    await user.selectOptions(await screen.findByLabelText("省"), "440000");
    await screen.findByRole("option", { name: "珠海市" });
    await user.selectOptions(await screen.findByLabelText("市"), "440400");
    await screen.findByRole("option", { name: "香洲区" });
    await user.selectOptions(await screen.findByLabelText("区 / 县"), "440402");
    await screen.findByText("文字标签：广东省 / 珠海市 / 香洲区");
    await user.click(screen.getByText("openai", { selector: "button" }));
    await user.click(screen.getByRole("button", { name: "保存偏好" }));

    await waitFor(() => expect(patchBody).toEqual(expect.objectContaining({
      weather_location: "广东省 / 珠海市 / 香洲区",
      weather_location_data: expect.objectContaining({
        schema_version: 2,
        administrative_coordinates: expect.objectContaining({
          coordinate_role: "administrative_center",
          latitude: 22.27,
          longitude: 113.57,
        }),
      }),
      news_topics: ["openai"],
      require_event_creation_approval: false,
      require_event_cancellation_approval: false,
    })));
  });

  it("keeps exact device coordinates when reverse geocoding is unavailable", async () => {
    let patchBody: Record<string, unknown> | undefined;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/preferences/me/") && (init?.method ?? "GET") === "GET") return new Response(JSON.stringify(preference));
      if (url.endsWith("/api/v1/preferences/me/") && init?.method === "PATCH") {
        patchBody = JSON.parse(String(init.body));
        return new Response(JSON.stringify({ ...preference, ...patchBody }));
      }
      if (url.endsWith("/api/v1/providers/catalog/")) return new Response(JSON.stringify({ weather_provider: "open_meteo", news_provider: "rss", news_feeds: [], topic_aliases: {}, news_topics: [], timezones: ["Asia/Shanghai"], locales: ["zh-CN"] }));
      if (url.endsWith("/api/v1/providers/locations/administrative-areas/")) return new Response(JSON.stringify([{ code: "440000", name: "广东省" }]));
      if (url.includes("/api/v1/providers/locations/current/")) return new Response(JSON.stringify({ provider: "device_geolocation", provider_location_id: "22.27000,113.57000", name: "当前位置", admin1: "", country: "", timezone: "Asia/Shanghai", label: "当前位置（精确坐标）", latitude: 22.27, longitude: 113.57, province: "", city: "", district: "" }));
      throw new Error(`Unexpected request: ${url}`);
    }));

    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("option", { name: "广东省" });
    await user.click(screen.getByRole("button", { name: "使用当前位置" }));

    await screen.findByText("文字标签：当前位置（精确坐标）");
    expect(screen.getByRole("status")).toHaveTextContent("请再手动选择省、市、区");
    await user.click(screen.getByRole("button", { name: "保存偏好" }));

    await waitFor(() => expect(patchBody).toEqual(expect.objectContaining({
      weather_location: "当前位置（精确坐标）",
      weather_location_data: expect.objectContaining({
        schema_version: 2,
        current_coordinates: expect.objectContaining({
          coordinate_role: "device_gps",
          latitude: 22.27,
          longitude: 113.57,
        }),
      }),
    })));
  });
});
