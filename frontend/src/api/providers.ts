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
}

export function getProviderCatalog() {
  return apiRequest<ProviderCatalog>("/api/v1/providers/catalog/");
}
