import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { updateCurrentUserPreference } from "../../api/preferences";
import { resolveCurrentLocation } from "../../api/providers";
import { preferenceQueryKey, useCurrentUserPreference } from "./hooks";
import { normalizeWeatherLocationData, withCurrentCoordinates } from "./weather-location";
import {
  clearCurrentDeviceWatch,
  hasLocationPermission,
  LOCATION_PERMISSION_GRANTED_EVENT,
  watchCurrentDeviceCoordinates,
  type DeviceCoordinates,
} from "../../native/geolocation";
import { isNativePlatform } from "../../platform";

function distanceInMeters(first: DeviceCoordinates, second: DeviceCoordinates): number {
  const radians = (degrees: number) => (degrees * Math.PI) / 180;
  const latitudeDelta = radians(second.latitude - first.latitude);
  const longitudeDelta = radians(second.longitude - first.longitude);
  const firstLatitude = radians(first.latitude);
  const secondLatitude = radians(second.latitude);
  const haversine =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(firstLatitude) * Math.cos(secondLatitude) * Math.sin(longitudeDelta / 2) ** 2;
  return 6_371_000 * 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
}

/** Keeps a previously saved, explicitly opted-in device location fresh in foreground. */
export function LocationTracker() {
  const queryClient = useQueryClient();
  const preference = useCurrentUserPreference();
  const latestPreference = useRef(preference.data);
  latestPreference.current = preference.data;
  const hasSavedCurrentLocation = Boolean(
    normalizeWeatherLocationData(preference.data?.weather_location_data)?.current_coordinates,
  );

  useEffect(() => {
    if (!hasSavedCurrentLocation) return;

    let active = true;
    let watchId: string | null = null;
    let isStarting = false;
    let isUpdating = false;
    let isPermissionGrantedInSession = false;
    let nativeAppListener: { remove: () => Promise<void> } | null = null;
    const savedCoordinates = normalizeWeatherLocationData(
      latestPreference.current?.weather_location_data,
    )?.current_coordinates;
    let lastUpdatedCoordinates: DeviceCoordinates | null = savedCoordinates
      ? {
          latitude: savedCoordinates.latitude,
          longitude: savedCoordinates.longitude,
          accuracyMeters: savedCoordinates.accuracy_meters,
        }
      : null;

    const stopWatching = () => {
      if (!watchId) return;
      void clearCurrentDeviceWatch(watchId);
      watchId = null;
    };

    const updateLocation = async (coordinates: DeviceCoordinates) => {
      if (!active || isUpdating) return;
      if (lastUpdatedCoordinates && distanceInMeters(lastUpdatedCoordinates, coordinates) < 100) return;
      isUpdating = true;
      try {
        const currentPreference = latestPreference.current;
        const currentData = normalizeWeatherLocationData(currentPreference?.weather_location_data);
        if (!currentPreference || !currentData?.current_coordinates) return;
        const candidate = await resolveCurrentLocation(
          coordinates.latitude,
          coordinates.longitude,
          Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai",
          currentPreference.locale || "zh-CN",
        );
        if (!active) return;
        const nextData = withCurrentCoordinates(currentData, candidate, coordinates.accuracyMeters);
        const updated = await updateCurrentUserPreference({
          weather_location: currentData.administrative_coordinates
            ? currentPreference.weather_location
            : nextData.label,
          weather_location_data: nextData,
        });
        lastUpdatedCoordinates = coordinates;
        latestPreference.current = updated;
        queryClient.setQueryData(preferenceQueryKey, updated);
      } catch {
        // A later location fix retries temporary geocoding or API failures.
      } finally {
        isUpdating = false;
      }
    };

    const startWatching = async () => {
      if (!active || document.hidden || watchId || isStarting) return;
      isStarting = true;
      try {
        if (!isPermissionGrantedInSession) {
          if (!(await hasLocationPermission())) return;
          isPermissionGrantedInSession = true;
        }
        if (!active || document.hidden) return;
        const id = await watchCurrentDeviceCoordinates((coordinates) => {
          void updateLocation(coordinates);
        });
        if (!active || document.hidden) {
          await clearCurrentDeviceWatch(id);
        } else {
          watchId = id;
        }
      } catch {
        // Location access can be revoked or temporarily unavailable.
      } finally {
        isStarting = false;
      }
    };

    const syncVisibility = () => {
      if (document.hidden) stopWatching();
      else void startWatching();
    };
    const onLocationPermissionGranted = () => {
      isPermissionGrantedInSession = true;
      void startWatching();
    };
    document.addEventListener("visibilitychange", syncVisibility);
    window.addEventListener(LOCATION_PERMISSION_GRANTED_EVENT, onLocationPermissionGranted);
    void startWatching();

    if (isNativePlatform()) {
      void import("@capacitor/app")
        .then(({ App }) => App.addListener("appStateChange", ({ isActive }) => {
          if (isActive) void startWatching();
          else stopWatching();
        }))
        .then((listener) => {
          if (active) nativeAppListener = listener;
          else void listener.remove();
        })
        .catch(() => {
          // The document visibility listener remains available as a fallback.
        });
    }

    return () => {
      active = false;
      stopWatching();
      if (nativeAppListener) void nativeAppListener.remove();
      document.removeEventListener("visibilitychange", syncVisibility);
      window.removeEventListener(LOCATION_PERMISSION_GRANTED_EVENT, onLocationPermissionGranted);
    };
  }, [hasSavedCurrentLocation, queryClient]);

  return null;
}
