import { Geolocation } from "@capacitor/geolocation";

export type DeviceCoordinates = {
  latitude: number;
  longitude: number;
  accuracyMeters?: number;
};

/**
 * Requests a location only after an explicit user action. Capacitor delegates
 * to Android on native builds and to the browser permission prompt on the web.
 */
export async function getCurrentDeviceCoordinates(): Promise<DeviceCoordinates> {
  const permission = await Geolocation.requestPermissions({ permissions: ["location"] });
  if (permission.location !== "granted") {
    throw new Error("未获得位置权限");
  }
  const position = await Geolocation.getCurrentPosition({
    enableHighAccuracy: true,
    timeout: 30_000,
    maximumAge: 5 * 60_000,
  });
  return {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracyMeters: position.coords.accuracy,
  };
}
