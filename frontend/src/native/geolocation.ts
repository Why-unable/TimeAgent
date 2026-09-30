import { Capacitor } from "@capacitor/core";
import { Geolocation } from "@capacitor/geolocation";

export const LOCATION_PERMISSION_GRANTED_EVENT = "time-agent:location-permission-granted";

export type DeviceCoordinates = {
  latitude: number;
  longitude: number;
  accuracyMeters?: number;
};

/**
 * Requests a location only after an explicit user action. Native builds use
 * Capacitor's permission prompt; browsers prompt from getCurrentPosition.
 */
export async function getCurrentDeviceCoordinates(): Promise<DeviceCoordinates> {
  if (Capacitor.isNativePlatform()) {
    const permission = await Geolocation.requestPermissions({ permissions: ["location"] });
    if (permission.location !== "granted") {
      throw new Error("未获得位置权限");
    }
  }

  const position = await Geolocation.getCurrentPosition({
    enableHighAccuracy: true,
    timeout: 30_000,
    maximumAge: 0,
  });
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(LOCATION_PERMISSION_GRANTED_EVENT));
  }
  return coordinatesFromPosition(position);
}

/** Returns true only when the user has already granted location access. */
export async function hasLocationPermission(): Promise<boolean> {
  try {
    return (await Geolocation.checkPermissions()).location === "granted";
  } catch {
    // Some browsers do not expose the Permissions API. Explicit location
    // requests still work there, but automatic updates remain opt-in only.
    return false;
  }
}

/** Watches for location changes while the opted-in app is in the foreground. */
export function watchCurrentDeviceCoordinates(
  onPosition: (coordinates: DeviceCoordinates) => void,
): Promise<string> {
  return Geolocation.watchPosition(
    {
      enableHighAccuracy: true,
      timeout: 60_000,
      maximumAge: 30_000,
      minimumUpdateInterval: 60_000,
    },
    (position) => {
      if (position) onPosition(coordinatesFromPosition(position));
    },
  );
}

export function clearCurrentDeviceWatch(id: string): Promise<void> {
  return Geolocation.clearWatch({ id });
}

function coordinatesFromPosition(position: Awaited<ReturnType<typeof Geolocation.getCurrentPosition>>): DeviceCoordinates {
  return {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracyMeters: position.coords.accuracy,
  };
}
