import { useQuery } from "@tanstack/react-query";
import { Download, LoaderCircle, RefreshCw, ShieldCheck, Smartphone, X } from "lucide-react";
import { useEffect } from "react";
import { QRCodeSVG } from "qrcode.react";

import { getLatestAndroidRelease } from "../api/app-updates";

type AndroidAppDownloadDialogProps = {
  open: boolean;
  onClose: () => void;
};

export function AndroidAppDownloadDialog({ open, onClose }: AndroidAppDownloadDialogProps) {
  const releaseQuery = useQuery({
    queryKey: ["android-download-release"],
    queryFn: getLatestAndroidRelease,
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  if (!open) return null;

  const release = releaseQuery.data?.release ?? null;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950/70 px-4 py-8 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="android-download-title"
        className="w-full max-w-xl overflow-hidden rounded-2xl border border-white/10 bg-white text-slate-900 shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700">
              <Smartphone size={20} />
            </span>
            <div className="min-w-0">
              <h2 id="android-download-title" className="text-lg font-semibold">
                下载 Time Agent
              </h2>
              <p className="mt-0.5 text-sm text-slate-500">Android 安装包</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid size-9 shrink-0 place-items-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
            aria-label="关闭下载窗口"
            title="关闭"
          >
            <X size={18} />
          </button>
        </header>

        <div className="p-5 sm:p-6">
          {releaseQuery.isPending && (
            <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-sm text-slate-500">
              <LoaderCircle className="animate-spin text-teal-700" size={24} />
              正在获取最新版本…
            </div>
          )}

          {releaseQuery.isError && (
            <div className="flex min-h-64 flex-col items-center justify-center gap-4 text-center">
              <p role="alert" className="text-sm text-red-700">
                暂时无法获取安装包信息，请稍后重试。
              </p>
              <button
                type="button"
                onClick={() => void releaseQuery.refetch()}
                className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800"
              >
                <RefreshCw size={16} />
                重新加载
              </button>
            </div>
          )}

          {releaseQuery.isSuccess && !release && (
            <div className="flex min-h-64 items-center justify-center text-center text-sm text-slate-600">
              Android 安装包暂未开放下载。
            </div>
          )}

          {release && (
            <div className="grid gap-6 sm:grid-cols-[190px_1fr] sm:items-center">
              <div className="mx-auto rounded-xl border border-slate-200 bg-white p-3 shadow-sm" aria-label="手机扫码下载">
                <QRCodeSVG
                  value={release.download_url}
                  size={164}
                  level="M"
                  marginSize={1}
                  title={`扫码下载 Time Agent ${release.version_name}`}
                />
              </div>

              <div className="min-w-0 text-center sm:text-left">
                <p className="text-base font-semibold">Time Agent {release.version_name}</p>
                <p className="mt-1 text-sm text-slate-500">
                  Android · {formatFileSize(release.size_bytes)}
                </p>
                <p className="mt-4 text-sm leading-6 text-slate-600">
                  使用手机扫描二维码，或在 Android 浏览器中直接下载安装包。
                </p>
                <a
                  href={release.download_url}
                  download
                  className="mt-4 inline-flex items-center gap-2 rounded-lg bg-teal-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-teal-800"
                >
                  <Download size={17} />
                  直接下载 APK
                </a>
              </div>
            </div>
          )}

          {release && (
            <div className="mt-6 flex gap-3 border-t border-slate-200 pt-4 text-xs leading-5 text-slate-500">
              <ShieldCheck className="mt-0.5 shrink-0 text-teal-700" size={16} />
              <p>首次安装时 Android 可能要求允许浏览器安装未知应用；系统安装器会在安装前再次请求确认。</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
