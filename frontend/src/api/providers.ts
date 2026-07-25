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
  name: string;
  admin1: string;
  country: string;
  timezone: string;
  label: string;
}

export function getProviderCatalog() {
  return apiRequest<ProviderCatalog>("/api/v1/providers/catalog/");
}

export function searchLocations(query: string, locale = "zh-CN") {
  return apiRequest<LocationCandidate[]>(
    `/api/v1/providers/locations/?q=${encodeURIComponent(query)}&locale=${encodeURIComponent(locale)}`,
  );
}
