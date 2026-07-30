import { AlarmClock, BellRing, Mail, MonitorSmartphone } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import type { NotificationPreference } from "../api/notifications";
import {
  useCreateWebPushSubscription,
  useDeleteWebPushSubscription,
  useNotificationDeliveries,
  useNotificationPreference,
  useUpdateNotificationPreference,
  useWebPushConfig,
  useWebPushSubscriptions,
} from "../features/notifications/hooks";
import {
  browserPushState,
  subscribeBrowser,
  unsubscribeBrowser,
} from "../features/notifications/web-push";
import {
  clearNativeNotificationDiagnostics,
  getNativeNotificationDiagnostics,
  type NotificationDiagnosticEntry,
} from "../native/notification-diagnostics";
import { isNativePlatform } from "../platform";
import { useCurrentUser } from "../features/accounts/hooks";
import {
  getNativeReminderPermissionState,
  requestNativeExactAlarmPermission,
  requestNativeReminderNotificationPermission,
  type NativeReminderPermissionState,
} from "../features/notifications/local-sync";
import {
  useCurrentUserPreference,
  useUpdateCurrentUserPreference,
} from "../features/preferences/hooks";

const stateLabels = {
  unsupported: "浏览器不支持推送通知",
  not_requested: "通知权限尚未请求",
  granted: "浏览器通知权限已授权",
  denied: "浏览器通知权限已拒绝",
};

export function NotificationSettingsPage() {
  const currentUser = useCurrentUser();
  const preference = useNotificationPreference();
  const deliveries = useNotificationDeliveries();
  const pushConfig = useWebPushConfig();
  const subscriptions = useWebPushSubscriptions();
  const updatePreference = useUpdateNotificationPreference();
  const userPreference = useCurrentUserPreference();
  const updateUserPreference = useUpdateCurrentUserPreference();
  const createSubscription = useCreateWebPushSubscription();
  const deleteSubscription = useDeleteWebPushSubscription();
  const [pushState, setPushState] = useState(() => browserPushState());
  const [pushError, setPushError] = useState("");
  const [diagnostics, setDiagnostics] = useState<NotificationDiagnosticEntry[]>([]);
  const [diagnosticsError, setDiagnosticsError] = useState("");
  const [nativePermission, setNativePermission] = useState<NativeReminderPermissionState | null>(null);
  const [nativePermissionError, setNativePermissionError] = useState("");
  const [nativePermissionBusy, setNativePermissionBusy] = useState(false);

  const refreshDiagnostics = async () => {
    if (!isNativePlatform()) return;
    try {
      setDiagnostics(await getNativeNotificationDiagnostics());
      setDiagnosticsError("");
    } catch (error) {
      setDiagnosticsError(error instanceof Error ? error.message : "无法读取设备通知诊断");
    }
  };

  useEffect(() => { void refreshDiagnostics(); }, []);

  const refreshNativePermission = async () => {
    if (!isNativePlatform()) return;
    try {
      setNativePermission(await getNativeReminderPermissionState());
      setNativePermissionError("");
    } catch (error) {
      setNativePermissionError(error instanceof Error ? error.message : "无法读取应用提醒权限状态");
    }
  };

  useEffect(() => {
    void refreshNativePermission();
    const refreshWhenReturning = () => {
      if (document.visibilityState === "visible") void refreshNativePermission();
    };
    window.addEventListener("focus", refreshWhenReturning);
    document.addEventListener("visibilitychange", refreshWhenReturning);
    return () => {
      window.removeEventListener("focus", refreshWhenReturning);
      document.removeEventListener("visibilitychange", refreshWhenReturning);
    };
  }, []);

  const enableNativeNotifications = async () => {
    setNativePermissionBusy(true);
    setNativePermissionError("");
    try {
      setNativePermission(await requestNativeReminderNotificationPermission());
    } catch (error) {
      setNativePermissionError(error instanceof Error ? error.message : "无法开启应用通知");
    } finally {
      setNativePermissionBusy(false);
    }
  };

  const enableExactAlarms = async () => {
    setNativePermissionBusy(true);
    setNativePermissionError("");
    try {
      setNativePermission(await requestNativeExactAlarmPermission());
    } catch (error) {
      setNativePermissionError(error instanceof Error ? error.message : "无法打开精确提醒设置");
    } finally {
      setNativePermissionBusy(false);
    }
  };

  const update = (field: keyof NotificationPreference, checked: boolean) => {
    updatePreference.mutate({ [field]: checked });
  };

  const enablePush = async () => {
    setPushError("");
    try {
      if (!pushConfig.data?.configured || !pushConfig.data.public_key) {
        throw new Error("后端尚未配置 VAPID 密钥");
      }
      await createSubscription.mutateAsync(
        await subscribeBrowser(pushConfig.data.public_key),
      );
      setPushState(browserPushState());
    } catch (error) {
      setPushState(browserPushState());
      setPushError(
        error instanceof Error && error.message === "notification_permission_denied"
          ? "你拒绝了通知权限，可在浏览器站点设置中重新开启。"
          : error instanceof Error
            ? error.message
            : "订阅失败",
      );
    }
  };

  const disablePush = async () => {
    setPushError("");
    try {
      await unsubscribeBrowser();
      await Promise.all(
        (subscriptions.data ?? []).map((item) => deleteSubscription.mutateAsync(item.id)),
      );
    } catch (error) {
      setPushError(error instanceof Error ? error.message : "取消订阅失败");
    }
  };

  if (preference.isLoading || userPreference.isLoading) return <p className="text-slate-400">正在加载通知设置…</p>;
  if (
    preference.isError ||
    !preference.data ||
    userPreference.isError ||
    !userPreference.data
  ) {
    return <p role="alert" className="text-red-300">无法读取通知设置，请确认已登录。</p>;
  }

  const subscribed = (subscriptions.data ?? []).some((item) => item.enabled);
  const invalidated = (subscriptions.data ?? []).some(
    (item) => !item.enabled && Boolean(item.invalidated_at),
  );
  const visibleDeliveries = (deliveries.data ?? []).filter(
    (item) => item.channel_type !== "console",
  );
  const deliveryHistory = currentUser.data?.is_staff ? visibleDeliveries : visibleDeliveries.slice(0, 10);
  return (
    <section className="mx-auto max-w-5xl space-y-8">
      <div>
        <h2 className="mt-2 text-3xl font-semibold">通知设置</h2>
        <p className="mt-3 text-slate-400">
          每个渠道独立投递、重试和审计。通知只发送给当前登录用户本人。
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <ChannelCard
          icon={BellRing}
          title="每日简报"
          description="系统会提前 5 分钟生成，并在设定时间通过已启用的简报渠道发送。"
        >
          <Toggle
            label="启用定时简报"
            checked={Boolean(userPreference.data?.daily_briefing_enabled)}
            onChange={(value) => updateUserPreference.mutate({ daily_briefing_enabled: value })}
          />
          <label className="block text-sm">
            <span className="text-slate-300">每日发送时间</span>
            <input
              type="time"
              value={userPreference.data?.briefing_time?.slice(0, 5) ?? "08:00"}
              disabled={updateUserPreference.isPending}
              onChange={(event) =>
                updateUserPreference.mutate({ briefing_time: `${event.target.value}:00` })
              }
              className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"
            />
          </label>
          {updateUserPreference.isError && (
            <p role="alert" className="text-sm text-red-300">
              定时简报设置保存失败：{updateUserPreference.error.message}
            </p>
          )}
        </ChannelCard>

        <ChannelCard
          icon={Mail}
          title="Email"
          description={`当前邮箱：${preference.data.email || "未设置"}`}
        >
          <Toggle label="提醒邮件" checked={Boolean(preference.data.reminder_email_enabled)} disabled={!preference.data.email} onChange={(value) => update("reminder_email_enabled", value)} />
          <Toggle label="简报邮件" checked={Boolean(preference.data.briefing_email_enabled)} disabled={!preference.data.email} onChange={(value) => update("briefing_email_enabled", value)} />
          {!preference.data.email && <p className="text-xs text-amber-300">请先在 Django 用户资料中设置有效邮箱。</p>}
        </ChannelCard>

        <ChannelCard icon={MonitorSmartphone} title="浏览器推送" description={stateLabels[pushState]}>
          <p className="text-xs text-slate-400">
            {pushConfig.data?.configured
              ? subscribed
                ? "已订阅此浏览器"
                : invalidated
                  ? "订阅已失效，请重新启用"
                  : "此浏览器尚未订阅"
              : "后端配置缺失"}
          </p>
          <p className="text-xs text-slate-400">仅适用于浏览器或 PWA；Android App 请使用“应用提醒”。</p>
          <div className="flex gap-3">
            <button type="button" onClick={enablePush} disabled={pushState === "unsupported" || pushState === "denied" || !pushConfig.data?.configured || subscribed} className="rounded-lg bg-cyan-300 px-3 py-2 text-sm font-medium text-slate-950 disabled:opacity-40">启用浏览器通知</button>
            <button type="button" onClick={disablePush} disabled={!subscribed} className="rounded-lg border border-white/15 px-3 py-2 text-sm disabled:opacity-40">取消订阅</button>
          </div>
          <Toggle label="提醒浏览器推送" checked={Boolean(preference.data.reminder_web_push_enabled)} disabled={!subscribed} onChange={(value) => update("reminder_web_push_enabled", value)} />
          <Toggle label="简报浏览器推送" checked={Boolean(preference.data.briefing_web_push_enabled)} disabled={!subscribed} onChange={(value) => update("briefing_web_push_enabled", value)} />
          {pushError && <p role="alert" className="text-sm text-red-300">{pushError}</p>}
        </ChannelCard>

        {isNativePlatform() && <ChannelCard
          icon={AlarmClock}
          title="应用提醒（Android）"
          description="由系统闹钟投递；应用退出后仍可提醒。"
        >
          <div className="space-y-2 rounded-xl bg-slate-950/60 p-4 text-sm">
            <p>应用通知：<span className={nativePermission?.display === "granted" ? "text-emerald-300" : "text-amber-300"}>{nativePermission?.display === "granted" ? "已允许" : "未允许"}</span></p>
            <p>精确提醒：<span className={nativePermission?.exactAlarm === "granted" ? "text-emerald-300" : "text-amber-300"}>{nativePermission?.exactAlarm === "granted" ? "已允许" : "未允许"}</span></p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={() => void enableNativeNotifications()} disabled={nativePermissionBusy || nativePermission?.display === "granted"} className="rounded-lg bg-cyan-300 px-3 py-2 text-sm font-medium text-slate-950 disabled:opacity-40">允许应用通知</button>
            <button type="button" onClick={() => void enableExactAlarms()} disabled={nativePermissionBusy || nativePermission?.display !== "granted" || nativePermission?.exactAlarm === "granted"} className="rounded-lg border border-cyan-300/50 px-3 py-2 text-sm text-cyan-100 disabled:opacity-40">开启精确提醒</button>
          </div>
          <p className="text-xs text-slate-400">先允许通知，再开启精确提醒。系统会打开 Android 的“闹钟和提醒”专属设置；返回此页后状态会自动刷新。</p>
          <p className="text-xs text-slate-400">为减少国产系统后台限制，请在系统设置中把 Time Agent 设为“不受限制”，并按设备品牌允许自启动/后台活动。</p>
          {nativePermissionError && <p role="alert" className="text-sm text-red-300">{nativePermissionError}</p>}
        </ChannelCard>}
      </div>

      <div className="rounded-2xl border border-white/10 bg-slate-900 p-6">
        <div className="flex items-center gap-3"><BellRing className="text-cyan-300" /><h3 className="text-xl font-semibold">最近投递</h3></div>
        {deliveries.isLoading && <p className="mt-4 text-slate-400">正在加载…</p>}
        {!deliveries.isLoading && deliveryHistory.length === 0 && <p className="mt-4 text-slate-400">暂无真实渠道投递记录。</p>}
        <ul className="mt-4 divide-y divide-white/10">
          {deliveryHistory.map((item) => (
            <li key={item.id} className="grid gap-2 py-4 sm:grid-cols-[1fr_auto]">
              <div>
                <p className="font-medium">{item.subject}</p>
                <p className="text-sm text-slate-400">{item.source_type} · {item.channel_type} · 尝试 {item.attempt_count} 次</p>
                {item.failure_reason && <p className="mt-1 text-sm text-red-300">{item.failure_code}: {item.failure_reason}</p>}
              </div>
              <span className={`h-fit rounded-full px-3 py-1 text-xs ${item.status === "sent" ? "bg-emerald-400/15 text-emerald-200" : item.status === "failed" ? "bg-red-400/15 text-red-200" : "bg-cyan-400/15 text-cyan-200"}`}>{item.status}</span>
            </li>
          ))}
        </ul>
      </div>

      {currentUser.data?.is_staff && isNativePlatform() && <div className="rounded-2xl border border-cyan-300/20 bg-slate-900 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><h3 className="text-xl font-semibold">设备通知诊断</h3><p className="mt-1 text-sm text-slate-400">仅保存在本机；“已触发”来自 Android 后台 Receiver，即使 App 已关闭也会记录。</p></div>
          <div className="flex gap-2"><button type="button" onClick={() => void refreshDiagnostics()} className="rounded-lg border border-white/15 px-3 py-2 text-sm">刷新</button><button type="button" onClick={() => void clearNativeNotificationDiagnostics().then(refreshDiagnostics)} className="rounded-lg border border-white/15 px-3 py-2 text-sm">清除</button></div>
        </div>
        {diagnosticsError && <p role="alert" className="mt-3 text-sm text-red-300">{diagnosticsError}</p>}
        {diagnostics.length === 0 ? <p className="mt-4 text-sm text-slate-400">尚无设备端排程或触发记录。</p> : <ul className="mt-4 space-y-2 text-sm">{diagnostics.slice().reverse().map((item, index) => <li key={`${item.recordedAt}-${index}`} className="rounded-xl bg-slate-950/60 p-3"><span className={item.kind === "fired" ? "text-emerald-300" : "text-cyan-300"}>{item.kind === "fired" ? "已触发" : "已登记"}</span><span className="ml-2 text-slate-300">#{item.notificationId} {item.title ?? ""}</span><p className="mt-1 text-xs text-slate-400">记录：{new Date(item.recordedAt).toLocaleString()} {item.scheduledAt ? ` · 计划：${new Date(item.scheduledAt).toLocaleString()} · 差值：${Math.round((item.recordedAt - item.scheduledAt) / 1000)} 秒` : ""}</p></li>)}</ul>}
      </div>}
    </section>
  );
}

function ChannelCard({ icon: Icon, title, description, children }: { icon: typeof Mail; title: string; description: string; children: ReactNode }) {
  return <div className="space-y-4 rounded-2xl border border-white/10 bg-slate-900 p-6"><div className="flex items-center gap-3"><Icon className="text-cyan-300" /><div><h3 className="font-semibold">{title}</h3><p className="text-xs text-slate-400">{description}</p></div></div>{children}</div>;
}

function Toggle({ label, checked, disabled = false, onChange }: { label: string; checked: boolean; disabled?: boolean; onChange: (value: boolean) => void }) {
  return <label className="flex items-center justify-between gap-4 rounded-xl bg-slate-950/60 px-4 py-3"><span className="text-sm">{label}</span><input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} className="h-5 w-5 accent-cyan-300" /></label>;
}
