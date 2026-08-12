import { useQuery } from "@tanstack/react-query";
import { Compass, Download, RefreshCw, ShieldCheck, Smartphone } from "lucide-react";
import { useState } from "react";

import { getLatestAndroidRelease } from "../api/app-updates";
import {
  downloadAndInstall,
  getInstalledAppInfo,
  openInstallPermissionSettings,
} from "../native/app-updater";
import { isNativePlatform } from "../platform";
import { requestOnboardingStart } from "../features/onboarding/storage";

export function AppSettingsPage() {
  const native = isNativePlatform();
  const [installed, setInstalled] = useState<Awaited<ReturnType<typeof getInstalledAppInfo>> | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [installing, setInstalling] = useState(false);
  const releaseQuery = useQuery({
    queryKey: ["android-update"],
    queryFn: async () => {
      const [manifest, appInfo] = await Promise.all([
        getLatestAndroidRelease(),
        native ? getInstalledAppInfo() : Promise.resolve(null),
      ]);
      setInstalled(appInfo);
      return manifest;
    },
    enabled: false,
  });
  const release = releaseQuery.data?.release ?? null;
  const updateAvailable = Boolean(release && installed && release.version_code > installed.versionCode);

  const check = async () => {
    setError("");
    setStatus("");
    const result = await releaseQuery.refetch();
    if (result.error) setError(result.error.message);
    else if (!result.data?.enabled) setStatus("管理员尚未启用应用内更新。当前版本仍可继续使用。");
    else if (result.data.release && installed && result.data.release.version_code <= installed.versionCode) {
      setStatus("当前已经是最新版本。");
    }
  };

  const install = async () => {
    if (!release || !installed) return;
    setInstalling(true);
    setError("");
    setStatus("正在安全下载并校验安装包，请不要关闭应用…");
    try {
      const currentAppInfo = await getInstalledAppInfo();
      setInstalled(currentAppInfo);
      if (!currentAppInfo.canRequestPackageInstalls) {
        await openInstallPermissionSettings();
        setStatus("请允许 Time Agent 安装未知应用，返回后再次点击更新。");
        return;
      }
      await downloadAndInstall({
        downloadUrl: release.download_url,
        sha256: release.sha256,
        expectedVersionCode: release.version_code,
        expectedSizeBytes: release.size_bytes,
      });
      setStatus("安装包校验通过，已交给 Android 系统安装器。请确认安装。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "更新失败，请稍后重试。");
      setStatus("");
    } finally {
      setInstalling(false);
    }
  };

  return (
    <section className="mx-auto max-w-3xl">
      <h2 className="mt-2 flex items-center gap-3 text-3xl font-semibold text-slate-900"><Smartphone className="text-teal-700" /> 应用设置</h2>
      <div className="mt-6 space-y-5 rounded-2xl border border-slate-200 bg-white p-6 text-slate-800 shadow-sm">
        <div>
          <p className="font-semibold">使用指南</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">重新查看首次使用引导，逐步探索“今天”、聊天、日程和偏好设置。</p>
        </div>
        <button type="button" onClick={requestOnboardingStart} className="inline-flex items-center gap-2 rounded-xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm font-medium text-teal-900 hover:bg-teal-100"><Compass size={17} /> 重新查看新手引导</button>
      </div>
      <div className="mt-5 space-y-5 rounded-2xl border border-slate-200 bg-white p-6 text-slate-800 shadow-sm">
        <div>
          <p className="font-semibold">软件更新</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">更新包必须来自 HTTPS，并通过 SHA-256、应用包名、版本号和签名证书四重校验；最终安装仍由 Android 系统确认。</p>
        </div>
        {installed && <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700">当前版本：{installed.versionName}（{installed.versionCode}）</p>}
        {!native && <p className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">检查并安装 APK 更新仅在 Android App 内可用。</p>}
        {release && (
          <div className="rounded-xl border border-teal-200 bg-teal-50 p-4">
            <p className="font-semibold text-teal-950">最新版本：{release.version_name}（{release.version_code}）</p>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-teal-900">{release.release_notes || "本次更新未提供说明。"}</p>
            <p className="mt-2 flex items-center gap-2 text-xs text-teal-800"><ShieldCheck size={15} /> 安装前自动验证签名与完整性</p>
          </div>
        )}
        {status && <p role="status" className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">{status}</p>}
        {error && <p role="alert" className="rounded-xl border border-red-300 bg-red-50 p-3 text-sm font-medium text-red-900">{error}</p>}
        <div className="flex flex-wrap gap-3">
          <button type="button" disabled={!native || releaseQuery.isFetching || installing} onClick={() => void check()} className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-medium text-white disabled:opacity-50"><RefreshCw size={17} className={releaseQuery.isFetching ? "animate-spin" : ""} /> {releaseQuery.isFetching ? "检查中…" : "检查更新"}</button>
          {updateAvailable && <button type="button" disabled={installing} onClick={() => void install()} className="inline-flex items-center gap-2 rounded-xl bg-teal-700 px-4 py-3 text-sm font-medium text-white disabled:opacity-50"><Download size={17} /> {installing ? "正在准备…" : "下载并更新"}</button>}
        </div>
      </div>
    </section>
  );
}
