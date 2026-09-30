import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  isNativePlatform: vi.fn(() => false),
  requestPermissions: vi.fn(),
  getCurrentPosition: vi.fn(),
  checkPermissions: vi.fn(),
  watchPosition: vi.fn(),
  clearWatch: vi.fn(),
}));

vi.mock("@capacitor/core", () => ({ Capacitor: { isNativePlatform: mocks.isNativePlatform } }));
vi.mock("@capacitor/geolocation", () => ({
  Geolocation: {
    requestPermissions: mocks.requestPermissions,
    getCurrentPosition: mocks.getCurrentPosition,
    checkPermissions: mocks.checkPermissions,
    watchPosition: mocks.watchPosition,
    clearWatch: mocks.clearWatch,
  },
}));

import { getCurrentDeviceCoordinates } from "../src/native/geolocation";

describe("device geolocation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.isNativePlatform.mockReturnValue(false);
    mocks.getCurrentPosition.mockResolvedValue({
      coords: { latitude: 22.27, longitude: 113.57, accuracy: 12 },
    });
    mocks.requestPermissions.mockResolvedValue({ location: "granted" });
  });

  it("uses the browser geolocation prompt instead of unsupported Capacitor permission requests", async () => {
    await expect(getCurrentDeviceCoordinates()).resolves.toEqual({
      latitude: 22.27,
      longitude: 113.57,
      accuracyMeters: 12,
    });

    expect(mocks.requestPermissions).not.toHaveBeenCalled();
    expect(mocks.getCurrentPosition).toHaveBeenCalledWith({
      enableHighAccuracy: true,
      timeout: 30_000,
      maximumAge: 0,
    });
  });

  it("requests location permission on native builds", async () => {
    mocks.isNativePlatform.mockReturnValue(true);

    await getCurrentDeviceCoordinates();

    expect(mocks.requestPermissions).toHaveBeenCalledWith({ permissions: ["location"] });
    expect(mocks.getCurrentPosition).toHaveBeenCalledOnce();
  });
});
