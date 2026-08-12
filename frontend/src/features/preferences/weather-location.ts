import type { LocationCandidate } from "../../api/providers";

export type StoredCoordinates = {
  provider: string;
  provider_location_id: string;
  coordinate_role: "administrative_center" | "device_gps";
  latitude: number;
  longitude: number;
  label?: string;
  accuracy_meters?: number;
};

export type WeatherLocationDataV2 = {
  schema_version: 2;
  provider: string;
  provider_location_id: string;
  adcode: string;
  name: string;
  admin1: string;
  country: string;
  timezone: string;
  label: string;
  province: string;
  city: string;
  district: string;
  administrative_coordinates?: StoredCoordinates;
  current_coordinates?: StoredCoordinates;
};

export function normalizeWeatherLocationData(value: unknown): WeatherLocationDataV2 | undefined {
  if (!value || typeof value !== "object") return undefined;
  const data = value as Record<string, unknown>;
  if (data.schema_version === 2) return data as WeatherLocationDataV2;
  if (typeof data.latitude !== "number" || typeof data.longitude !== "number") return undefined;
  const provider = text(data.provider);
  const role = provider === "device_geolocation" ? "device_gps" : "administrative_center";
  const coordinates: StoredCoordinates = {
    provider: provider || "open_meteo",
    provider_location_id: text(data.provider_location_id),
    coordinate_role: role,
    latitude: data.latitude,
    longitude: data.longitude,
    label: text(data.label),
  };
  return {
    schema_version: 2,
    provider,
    provider_location_id: text(data.provider_location_id),
    adcode: sixDigitCode(data.adcode) || sixDigitCode(data.provider_location_id),
    name: text(data.name),
    admin1: text(data.admin1),
    country: text(data.country),
    timezone: text(data.timezone),
    label: text(data.label),
    province: text(data.province),
    city: text(data.city),
    district: text(data.district),
    ...(role === "device_gps"
      ? { current_coordinates: coordinates }
      : { administrative_coordinates: coordinates }),
  };
}

export function withAdministrativeCoordinates(
  existing: unknown,
  candidate: LocationCandidate,
): WeatherLocationDataV2 {
  const previous = normalizeWeatherLocationData(existing);
  return {
    schema_version: 2,
    provider: candidate.provider,
    provider_location_id: candidate.provider_location_id,
    adcode: candidate.adcode ?? "",
    name: candidate.name,
    admin1: candidate.admin1,
    country: candidate.country,
    timezone: candidate.timezone,
    label: candidate.label,
    province: candidate.province ?? "",
    city: candidate.city ?? "",
    district: candidate.district ?? "",
    administrative_coordinates: {
      provider: candidate.provider,
      provider_location_id: candidate.provider_location_id,
      coordinate_role: "administrative_center",
      latitude: candidate.latitude,
      longitude: candidate.longitude,
      label: candidate.label,
    },
    ...(previous?.current_coordinates
      ? { current_coordinates: previous.current_coordinates }
      : {}),
  };
}

export function withCurrentCoordinates(
  existing: unknown,
  candidate: LocationCandidate,
  accuracyMeters?: number,
): WeatherLocationDataV2 {
  const previous = normalizeWeatherLocationData(existing);
  const label = previous?.administrative_coordinates ? previous.label : candidate.label;
  return {
    schema_version: 2,
    provider: previous?.provider ?? candidate.provider,
    provider_location_id: previous?.provider_location_id ?? candidate.provider_location_id,
    adcode: previous?.adcode || candidate.adcode || "",
    name: previous?.name || candidate.name,
    admin1: previous?.admin1 || candidate.admin1,
    country: previous?.country || candidate.country,
    timezone: previous?.timezone || candidate.timezone,
    label,
    province: previous?.province || candidate.province || "",
    city: previous?.city || candidate.city || "",
    district: previous?.district || candidate.district || "",
    ...(previous?.administrative_coordinates
      ? { administrative_coordinates: previous.administrative_coordinates }
      : {}),
    current_coordinates: {
      provider: "device_geolocation",
      provider_location_id: candidate.provider_location_id,
      coordinate_role: "device_gps",
      latitude: candidate.latitude,
      longitude: candidate.longitude,
      label: candidate.label,
      ...(accuracyMeters === undefined ? {} : { accuracy_meters: accuracyMeters }),
    },
  };
}

export function withoutAdministrativeCoordinates(existing: unknown): WeatherLocationDataV2 | undefined {
  const previous = normalizeWeatherLocationData(existing);
  if (!previous?.current_coordinates) return undefined;
  const current = previous.current_coordinates;
  return {
    schema_version: 2,
    provider: current.provider,
    provider_location_id: current.provider_location_id,
    adcode: "",
    name: "手机当前位置",
    admin1: "",
    country: previous.country,
    timezone: previous.timezone,
    label: current.label || "当前位置（精确坐标）",
    province: "",
    city: "",
    district: "",
    current_coordinates: current,
  };
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function sixDigitCode(value: unknown): string {
  const candidate = text(value);
  return /^\d{6}$/.test(candidate) ? candidate : "";
}
