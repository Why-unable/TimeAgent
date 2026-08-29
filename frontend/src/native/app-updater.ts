import { registerPlugin } from "@capacitor/core";

type InstalledAppInfo = {
  versionCode: number;
  versionName: string;
  canRequestPackageInstalls: boolean;
};

type InstallOptions = {
  downloadUrl: string;
  sha256: string;
  expectedVersionCode: number;
  expectedVersionName: string;
  expectedSizeBytes: number;
};

interface AppUpdaterPlugin {
  getInstalledAppInfo(): Promise<InstalledAppInfo>;
  openInstallPermissionSettings(): Promise<void>;
  downloadAndInstall(options: InstallOptions): Promise<{ started: boolean }>;
}

const AppUpdater = registerPlugin<AppUpdaterPlugin>("AppUpdater");

export function getInstalledAppInfo() {
  return AppUpdater.getInstalledAppInfo();
}

export function openInstallPermissionSettings() {
  return AppUpdater.openInstallPermissionSettings();
}

export function downloadAndInstall(options: InstallOptions) {
  return AppUpdater.downloadAndInstall(options);
}
