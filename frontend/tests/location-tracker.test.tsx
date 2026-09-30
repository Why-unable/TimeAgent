import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocationTracker } from "../src/features/preferences/location-tracker";
import type { DeviceCoordinates } from "../src/native/geolocation";

const geolocationMocks = vi.hoisted(() => ({
  LOCATION_PERMISSION_GRANTED_EVENT: "time-agent:location-permission-granted",
  hasLocationPermission: vi.fn(),
  watchCurrentDeviceCoordinates: vi.fn(),
  clearCurrentDeviceWatch: vi.fn(),
}));

vi.mock("../src/native/geolocation", () => geolocationMocks);

const savedPreference = {
  timezone: "Asia/Shanghai",
  locale: "zh-CN",
  workday_start: "09:00:00",
  workday_end: "18:00:00",
  default_event_duration_minutes: 60,
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
    administrative_coordinates: {
      provider: "open_meteo",
      provider_location_id: "admin-1",
      coordinate_role: "administrative_center",
      latitude: 22.27,
      longitude: 113.57,
      label: "广东省 / 珠海市 / 香洲区",
    },
    current_coordinates: {
      provider: "device_geolocation",
      provider_location_id: "22.27000,113.57000",
      coordinate_role: "device_gps",
      latitude: 22.27,
      longitude: 113.57,
      label: "当前位置（精确坐标）",
      accuracy_meters: 12,
    },
  },
};

describe("LocationTracker", () => {
  beforeEach(() => {
    geolocationMocks.hasLocationPermission.mockResolvedValue(true);
    geolocationMocks.watchCurrentDeviceCoordinates.mockImplementation(async (onPosition) => {
      queueMicrotask(() => onPosition({ latitude: 22.28, longitude: 113.58, accuracyMeters: 8 }));
      return "watch-1";
    });
    geolocationMocks.clearCurrentDeviceWatch.mockResolvedValue(undefined);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("automatically saves meaningful location changes across authenticated app pages", async () => {
    let patchBody: Record<string, unknown> | undefined;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/preferences/me/") && (init?.method ?? "GET") === "GET") {
        return new Response(JSON.stringify(savedPreference));
      }
      if (url.includes("/api/v1/providers/locations/current/")) {
        return new Response(JSON.stringify({
          provider: "device_geolocation",
          provider_location_id: "22.28000,113.58000",
          name: "当前位置",
          admin1: "广东省",
          country: "中国",
          timezone: "Asia/Shanghai",
          label: "当前位置（精确坐标）",
          latitude: 22.28,
          longitude: 113.58,
          province: "广东省",
          city: "珠海市",
          district: "香洲区",
        }));
      }
      if (url.endsWith("/api/v1/preferences/me/") && init?.method === "PATCH") {
        patchBody = JSON.parse(String(init.body));
        return new Response(JSON.stringify({ ...savedPreference, ...patchBody }));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><LocationTracker /></QueryClientProvider>);

    await waitFor(() => expect(patchBody).toEqual(expect.objectContaining({
      weather_location: "广东省 / 珠海市 / 香洲区",
      weather_location_data: expect.objectContaining({
        current_coordinates: expect.objectContaining({
          latitude: 22.28,
          longitude: 113.58,
          accuracy_meters: 8,
        }),
        administrative_coordinates: expect.objectContaining({ latitude: 22.27, longitude: 113.57 }),
      }),
    })));
  });

  it("starts tracking after the user grants location permission while the app is open", async () => {
    geolocationMocks.hasLocationPermission.mockResolvedValue(false);
    geolocationMocks.watchCurrentDeviceCoordinates.mockImplementationOnce(async () => "watch-reauthorized");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(savedPreference))));

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(<QueryClientProvider client={queryClient}><LocationTracker /></QueryClientProvider>);
    await waitFor(() => expect(geolocationMocks.hasLocationPermission).toHaveBeenCalled());
    expect(geolocationMocks.watchCurrentDeviceCoordinates).not.toHaveBeenCalled();

    geolocationMocks.hasLocationPermission.mockResolvedValue(true);
    window.dispatchEvent(new Event(geolocationMocks.LOCATION_PERMISSION_GRANTED_EVENT));

    await waitFor(() => expect(geolocationMocks.watchCurrentDeviceCoordinates).toHaveBeenCalledOnce());
    view.unmount();
  });

  it("ignores a queued position callback after the app enters the background", async () => {
    let deliverPosition: ((coordinates: DeviceCoordinates) => void) | undefined;
    geolocationMocks.watchCurrentDeviceCoordinates.mockImplementation(async (onPosition) => {
      deliverPosition = onPosition;
      return "watch-background";
    });
    const requestedUrls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.endsWith("/api/v1/preferences/me/")) {
        return new Response(JSON.stringify(savedPreference));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(<QueryClientProvider client={queryClient}><LocationTracker /></QueryClientProvider>);
    await waitFor(() => expect(deliverPosition).toBeDefined());

    const originalHiddenDescriptor = Object.getOwnPropertyDescriptor(document, "hidden");
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    document.dispatchEvent(new Event("visibilitychange"));
    await waitFor(() => expect(geolocationMocks.clearCurrentDeviceWatch).toHaveBeenCalledWith("watch-background"));

    deliverPosition?.({ latitude: 22.30, longitude: 113.60, accuracyMeters: 8 });
    await Promise.resolve();
    expect(requestedUrls.some((url) => url.includes("/api/v1/providers/locations/current/"))).toBe(false);
    expect(requestedUrls.filter((url) => url.endsWith("/api/v1/preferences/me/")).length).toBe(1);

    view.unmount();
    if (originalHiddenDescriptor) {
      Object.defineProperty(document, "hidden", originalHiddenDescriptor);
    } else {
      Reflect.deleteProperty(document, "hidden");
    }
    document.dispatchEvent(new Event("visibilitychange"));
  });
});
