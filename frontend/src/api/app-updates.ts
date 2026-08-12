import { apiRequest } from "./client";

export type AndroidRelease = {
  version_code: number;
  version_name: string;
  download_url: string;
  sha256: string;
  size_bytes: number;
  release_notes: string;
  published_at: string;
  minimum_supported_version_code: number;
};

export type AndroidUpdateResponse = {
  enabled: boolean;
  release: AndroidRelease | null;
};

export function getLatestAndroidRelease() {
  return apiRequest<AndroidUpdateResponse>("/api/v1/app-updates/android/latest/");
}
