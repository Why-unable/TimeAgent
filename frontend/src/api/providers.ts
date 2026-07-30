import { apiRequest } from "./client";

export interface ProviderFeed {
  name: string;
  publisher: string;
  url: string;
  topics: string[];
}

export interface ProviderCatalog {
  weather_provider: string;
  news_provider: string;
  news_feeds: ProviderFeed[];
  topic_aliases: Record<string, string[]>;
  news_topics: string[];
  timezones: string[];
  locales: string[];
}

export interface LocationCandidate {
  provider: string;
  provider_location_id: string;
  name: string;
  admin1: string;
  country: string;
  timezone: string;
  label: string;
  latitude: number;
  longitude: number;
  province?: string;
  city?: string;
  district?: string;
}

export interface AdministrativeAreaOption {
  code: string;
  name: string;
}

export function getProviderCatalog() {
  return apiRequest<ProviderCatalog>("/api/v1/providers/catalog/");
}

export function searchLocations(query: string, locale = "zh-CN", signal?: AbortSignal) {
  return apiRequest<LocationCandidate[]>(
    `/api/v1/providers/locations/?q=${encodeURIComponent(query)}&locale=${encodeURIComponent(locale)}`,
    { signal },
  );
}

export function getAdministrativeAreas(provinceCode = "", cityCode = "") {
  const query = new URLSearchParams();
  if (provinceCode) query.set("province_code", provinceCode);
  if (cityCode) query.set("city_code", cityCode);
  const suffix = query.size ? `?${query}` : "";
  return apiRequest<AdministrativeAreaOption[]>(`/api/v1/providers/locations/administrative-areas/${suffix}`);
}

export function resolveCurrentLocation(
  latitude: number,
  longitude: number,
  timezone: string,
  locale = "zh-CN",
) {
  const query = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    timezone,
    locale,
  });
  return apiRequest<LocationCandidate>(`/api/v1/providers/locations/current/?${query}`);
}

export function resolveAdministrativeLocation(
  province: string,
  city: string,
  district: string,
  locale = "zh-CN",
) {
  const query = new URLSearchParams({ province, city, district, locale });
  return apiRequest<LocationCandidate>(`/api/v1/providers/locations/resolve/?${query}`);
}
