import { BellRing, Mail, MonitorSmartphone } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

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

const stateLabels = {
  unsupported: "浏览器不支持 Web Push",
  not_requested: "通知权限尚未请求",
  granted: "浏览器通知权限已授权",
  denied: "浏览器通知权限已拒绝",
};

export function NotificationSettingsPage() {
  const preference = useNotificationPreference();
  const deliveries = useNotificationDeliveries();
  const pushConfig = useWebPushConfig();
  const subscriptions = useWebPushSubscriptions();
  const updatePreference = useUpdateNotificationPreference();
  const createSubscription = useCreateWebPushSubscription();
  const deleteSubscription = useDeleteWebPushSubscription();
  const [pushState, setPushState] = useState(() => browserPushState());
  const [pushError, setPushError] = useState("");

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

  if (preference.isLoading) return <p className="text-slate-400">正在加载通知设置…</p>;
  if (preference.isError || !preference.data) {
    return <p role="alert" className="text-red-300">无法读取通知设置，请确认已登录。</p>;
  }

  const subscribed = (subscriptions.data ?? []).some((item) => item.enabled);
  const invalidated = (subscriptions.data ?? []).some(
    (item) => !item.enabled && Boolean(item.invalidated_at),
  );
  const visibleDeliveries = (deliveries.data ?? []).filter(
    (item) => item.channel_type !== "console",
  );
  return (
    <section className="mx-auto max-w-5xl space-y-8">
      <div>
        <p className="text-sm font-medium text-cyan-300">Phase 9 · 外部通知</p>
        <h2 className="mt-2 text-3xl font-semibold">通知设置</h2>
        <p className="mt-3 text-slate-400">
          每个渠道独立投递、重试和审计。通知只发送给当前登录用户本人。
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <ChannelCard
          icon={Mail}
          title="Email"
          description={`当前邮箱：${preference.data.email || "未设置"}`}
        >
          <Toggle label="提醒邮件" checked={Boolean(preference.data.reminder_email_enabled)} disabled={!preference.data.email} onChange={(value) => update("reminder_email_enabled", value)} />
          <Toggle label="简报邮件" checked={Boolean(preference.data.briefing_email_enabled)} disabled={!preference.data.email} onChange={(value) => update("briefing_email_enabled", value)} />
          {!preference.data.email && <p className="text-xs text-amber-300">请先在 Django 用户资料中设置有效邮箱。</p>}
        </ChannelCard>

        <ChannelCard icon={MonitorSmartphone} title="Web Push" description={stateLabels[pushState]}>
          <p className="text-xs text-slate-400">
            {pushConfig.data?.configured
              ? subscribed
                ? "已订阅此浏览器"
                : invalidated
                  ? "订阅已失效，请重新启用"
                  : "此浏览器尚未订阅"
              : "后端配置缺失"}
          </p>
          <div className="flex gap-3">
            <button type="button" onClick={enablePush} disabled={pushState === "unsupported" || pushState === "denied" || !pushConfig.data?.configured || subscribed} className="rounded-lg bg-cyan-300 px-3 py-2 text-sm font-medium text-slate-950 disabled:opacity-40">启用浏览器通知</button>
            <button type="button" onClick={disablePush} disabled={!subscribed} className="rounded-lg border border-white/15 px-3 py-2 text-sm disabled:opacity-40">取消订阅</button>
          </div>
          <Toggle label="提醒 Push" checked={Boolean(preference.data.reminder_web_push_enabled)} disabled={!subscribed} onChange={(value) => update("reminder_web_push_enabled", value)} />
          <Toggle label="简报 Push" checked={Boolean(preference.data.briefing_web_push_enabled)} disabled={!subscribed} onChange={(value) => update("briefing_web_push_enabled", value)} />
          {pushError && <p role="alert" className="text-sm text-red-300">{pushError}</p>}
        </ChannelCard>
      </div>

      <div className="rounded-2xl border border-white/10 bg-slate-900 p-6">
        <div className="flex items-center gap-3"><BellRing className="text-cyan-300" /><h3 className="text-xl font-semibold">最近投递</h3></div>
        {deliveries.isLoading && <p className="mt-4 text-slate-400">正在加载…</p>}
        {!deliveries.isLoading && visibleDeliveries.length === 0 && <p className="mt-4 text-slate-400">暂无真实渠道投递记录。</p>}
        <ul className="mt-4 divide-y divide-white/10">
          {visibleDeliveries.map((item) => (
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
    </section>
  );
}

function ChannelCard({ icon: Icon, title, description, children }: { icon: typeof Mail; title: string; description: string; children: ReactNode }) {
  return <div className="space-y-4 rounded-2xl border border-white/10 bg-slate-900 p-6"><div className="flex items-center gap-3"><Icon className="text-cyan-300" /><div><h3 className="font-semibold">{title}</h3><p className="text-xs text-slate-400">{description}</p></div></div>{children}</div>;
}

function Toggle({ label, checked, disabled = false, onChange }: { label: string; checked: boolean; disabled?: boolean; onChange: (value: boolean) => void }) {
  return <label className="flex items-center justify-between gap-4 rounded-xl bg-slate-950/60 px-4 py-3"><span className="text-sm">{label}</span><input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} className="h-5 w-5 accent-cyan-300" /></label>;
}
