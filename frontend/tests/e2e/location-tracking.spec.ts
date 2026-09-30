import { expect, test } from "@playwright/test";

const administrativeCoordinates = {
  provider: "open_meteo",
  provider_location_id: "admin-1",
  coordinate_role: "administrative_center",
  latitude: 22.27,
  longitude: 113.57,
  label: "广东省 / 珠海市 / 香洲区",
};

const initialPreference = {
  timezone: "Asia/Shanghai",
  locale: "zh-CN",
  workday_start: "09:00:00",
  workday_end: "18:00:00",
  sleep_start: "23:00:00",
  sleep_end: "07:00:00",
  default_event_duration_minutes: 60,
  preferred_focus_periods: [],
  default_reminder_offsets: [],
  weather_location: "广东省 / 珠海市 / 香洲区",
  weather_location_data: {
    schema_version: 2,
    provider: "open_meteo",
    provider_location_id: "admin-1",
    adcode: "440402",
    name: "香洲区",
    admin1: "广东省",
    country: "中国",
    timezone: "Asia/Shanghai",
    label: "广东省 / 珠海市 / 香洲区",
    province: "广东省",
    city: "珠海市",
    district: "香洲区",
    administrative_coordinates: administrativeCoordinates,
  },
  weather_forecast_days: 3,
  require_event_creation_approval: false,
  require_event_cancellation_approval: false,
  news_topics: [],
  briefing_time: "08:00:00",
  planning_rules: {},
  updated_at: "2026-09-30T00:00:00Z",
};

test("tracks an opted-in location in foreground and stops in background or after permission revocation", async ({ page }) => {
  test.setTimeout(30_000);
  const context = page.context();
  await context.grantPermissions(["geolocation"], { origin: "http://127.0.0.1:4173" });
  await context.setGeolocation({ latitude: 22.27, longitude: 113.57 });
  await page.addInitScript(() => {
    window.localStorage.setItem("time-agent:onboarding:1:v1", "completed");
  });

  let preference = structuredClone(initialPreference);
  const preferencePatches: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/auth/me/", (route) =>
    route.fulfill({
      json: { id: 1, email: "location-e2e@example.test", display_name: "Location E2E", is_staff: false },
    }),
  );
  await page.route("**/api/v1/preferences/me/", async (route) => {
    if (route.request().method() === "PATCH") {
      const patch = route.request().postDataJSON() as Record<string, unknown>;
      preferencePatches.push(patch);
      preference = { ...preference, ...patch };
    }
    await route.fulfill({ json: preference });
  });
  await page.route("**/api/v1/providers/catalog/", (route) =>
    route.fulfill({
      json: {
        weather_provider: "Open-Meteo",
        news_provider: "RSS",
        news_feeds: [],
        topic_aliases: {},
        news_topics: [],
        timezones: ["Asia/Shanghai"],
        locales: ["zh-CN"],
      },
    }),
  );
  await page.route("**/api/v1/providers/locations/administrative-areas/**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/providers/locations/current/**", async (route) => {
    const url = new URL(route.request().url());
    const latitude = Number(url.searchParams.get("latitude"));
    const longitude = Number(url.searchParams.get("longitude"));
    await route.fulfill({
      json: {
        provider: "device_geolocation",
        provider_location_id: `${latitude.toFixed(5)},${longitude.toFixed(5)}`,
        name: "当前位置",
        admin1: "广东省",
        country: "中国",
        timezone: url.searchParams.get("timezone") ?? "Asia/Shanghai",
        label: "当前位置（精确坐标）",
        latitude,
        longitude,
        province: "广东省",
        city: "珠海市",
        district: "香洲区",
      },
    });
  });
  await page.route("**/api/v1/today/", (route) =>
    route.fulfill({
      json: {
        date: "2026-09-30",
        timezone: "Asia/Shanghai",
        generated_at: "2026-09-30T00:00:00Z",
        day_start_at: "2026-09-29T16:00:00Z",
        day_end_at: "2026-09-30T16:00:00Z",
        events: [],
        planned_tasks: [],
        due_tasks: [],
        overdue_tasks: [],
        pending_reminders: [],
        conflicts: [],
        next_event: null,
        minutes_until_next_event: null,
      },
    }),
  );
  await page.route("**/api/v1/tasks/**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/events/**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/reminders/**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/insights/", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/integrations/calendar/connections/", (route) =>
    route.fulfill({ json: [] }),
  );

  await page.goto("/settings/time");
  await page.getByRole("button", { name: "使用当前位置" }).click();
  await expect(page.getByText(/已保存手机 GPS 精确坐标/)).toBeVisible();
  await page.getByRole("button", { name: "保存偏好" }).click();
  await expect(page.getByText("偏好已保存。", { exact: true })).toBeVisible();
  expect(preferencePatches).toHaveLength(1);
  expect(preferencePatches[0].weather_location_data).toMatchObject({
    administrative_coordinates: administrativeCoordinates,
    current_coordinates: {
      latitude: 22.27,
      longitude: 113.57,
      coordinate_role: "device_gps",
    },
  });

  // The tracker belongs to the authenticated app shell and remains active across routes.
  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "今天" })).toBeVisible();
  await context.setGeolocation({ latitude: 22.28, longitude: 113.58 });
  await expect.poll(() => preferencePatches.length).toBe(2);
  expect(preferencePatches[1].weather_location).toBe("广东省 / 珠海市 / 香洲区");
  expect(preferencePatches[1].weather_location_data).toMatchObject({
    administrative_coordinates: administrativeCoordinates,
    current_coordinates: { latitude: 22.28, longitude: 113.58 },
  });

  await page.evaluate(() => {
    let hidden = false;
    Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => (hidden ? "hidden" : "visible"),
    });
    (window as Window & { setTestVisibility?: (value: boolean) => void }).setTestVisibility = (value) => {
      hidden = value;
      document.dispatchEvent(new Event("visibilitychange"));
    };
  });
  await page.evaluate(() => (window as Window & { setTestVisibility?: (value: boolean) => void }).setTestVisibility?.(true));
  await context.setGeolocation({ latitude: 22.30, longitude: 113.60 });
  await page.waitForTimeout(500);
  expect(preferencePatches).toHaveLength(2);

  await page.evaluate(() => (window as Window & { setTestVisibility?: (value: boolean) => void }).setTestVisibility?.(false));
  await expect.poll(() => preferencePatches.length).toBe(3);
  expect(preferencePatches[2].weather_location_data).toMatchObject({
    administrative_coordinates: administrativeCoordinates,
    current_coordinates: { latitude: 22.30, longitude: 113.60 },
  });

  await context.clearPermissions();
  await page.evaluate(() => (window as Window & { setTestVisibility?: (value: boolean) => void }).setTestVisibility?.(true));
  await page.evaluate(() => (window as Window & { setTestVisibility?: (value: boolean) => void }).setTestVisibility?.(false));
  await context.setGeolocation({ latitude: 22.32, longitude: 113.62 });
  await page.waitForTimeout(500);
  expect(preferencePatches).toHaveLength(3);
});
