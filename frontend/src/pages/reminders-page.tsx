import { zodResolver } from "@hookform/resolvers/zod";
import { Bell, CircleAlert, Plus, X } from "lucide-react";
import type { ReactNode } from "react";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { Reminder } from "../api/reminders";
import { useEvents } from "../features/events/hooks";
import { useTasks } from "../features/tasks/hooks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import {
  useCancelReminder,
  useCreateReminder,
  useReminders,
} from "../features/reminders/hooks";
import { ScheduleWorkspaceTabs } from "../features/workspace/schedule-workspace-tabs";
import { formatInUserTimezone, toUtcISOString } from "../utils/datetime";

const reminderFormSchema = z
  .object({
    title: z.string().trim().min(1, "请输入提醒内容").max(255),
    trigger_at: z.string().min(1, "请选择提醒时间"),
    target_type: z.enum(["custom", "calendar_event", "task"]),
    target_id: z.string(),
  })
  .superRefine((values, context) => {
    if (values.target_type !== "custom" && !values.target_id) {
      context.addIssue({
        code: "custom",
        path: ["target_id"],
        message: "请选择关联对象",
      });
    }
  });

type ReminderForm = z.infer<typeof reminderFormSchema>;

const statusLabels: Record<NonNullable<Reminder["status"]>, string> = {
  pending: "等待发送",
  queued: "已进入队列",
  sending: "正在发送",
  sent: "发送成功",
  failed: "发送失败",
  cancelled: "已取消",
  missed: "已错过",
};

const statusStyles: Record<NonNullable<Reminder["status"]>, string> = {
  pending: "bg-sky-400/10 text-sky-200",
  queued: "bg-violet-400/10 text-violet-200",
  sending: "bg-amber-400/10 text-amber-200",
  sent: "bg-emerald-400/10 text-emerald-200",
  failed: "bg-red-400/10 text-red-200",
  cancelled: "bg-slate-400/10 text-slate-300",
  missed: "bg-orange-400/10 text-orange-200",
};

const cancellableStatuses = new Set<Reminder["status"]>(["pending", "queued", "failed"]);
const pendingStatuses = new Set<Reminder["status"]>(["pending", "queued", "sending", "failed"]);
const SENT_HISTORY_LIMIT = 10;
const PENDING_PAGE_SIZE = 10;

export function RemindersPage() {
  const preference = useCurrentUserPreference();
  const reminders = useReminders();
  const createMutation = useCreateReminder();
  const cancelMutation = useCancelReminder();
  const idempotencyKey = useRef(crypto.randomUUID());
  const timezone = preference.data?.timezone ?? "Asia/Shanghai";
  const locale = preference.data?.locale ?? "zh-CN";
  const tasks = useTasks();
  const events = useEvents({});
  const form = useForm<ReminderForm>({
    resolver: zodResolver(reminderFormSchema),
    defaultValues: { title: "", trigger_at: "", target_type: "custom", target_id: "" },
  });
  const [pendingLimit, setPendingLimit] = useState(PENDING_PAGE_SIZE);
  const allReminders = reminders.data ?? [];
  const pendingReminders = allReminders.filter((item) => pendingStatuses.has(item.status));
  const historicalReminders = allReminders
    .filter((item) => item.status === "sent" || item.status === "missed")
    .slice()
    .sort((left, right) => Date.parse(right.sent_at ?? right.updated_at) - Date.parse(left.sent_at ?? left.updated_at))
    .slice(0, SENT_HISTORY_LIMIT);
  const visiblePendingReminders = pendingReminders.slice(0, pendingLimit);

  const onSubmit = form.handleSubmit((values) => {
    createMutation.mutate(
      {
        title: values.title.trim(),
        trigger_at: toUtcISOString(values.trigger_at, timezone),
        timezone,
        channel: "console",
        target_type: values.target_type,
        target_id: values.target_type === "custom" ? null : values.target_id,
        deduplication_key: idempotencyKey.current,
      },
      {
        onSuccess: () => {
          form.reset();
          idempotencyKey.current = crypto.randomUUID();
        },
      },
    );
  });

  return (
    <section className="mx-auto max-w-5xl">
      <ScheduleWorkspaceTabs />
      {/* Desktop heading */}
      <div className="mt-2 hidden items-center gap-3 lg:flex">
        <Bell className="text-cyan-300" />
        <h2 className="text-3xl font-semibold">提醒</h2>
      </div>
      <p className="mt-3 hidden text-slate-400 lg:block">创建自定义提醒，并查看确定性投递状态。</p>

      {/* Mobile description + primary action */}
      <p className="mt-4 text-base text-slate-400 lg:hidden">
        创建自定义提醒，并查看确定性投递状态。
      </p>
      {/* sr-only heading so tests and screen readers can still target 提醒 */}
      <h2 className="sr-only lg:hidden">提醒</h2>

      <form
        onSubmit={onSubmit}
        className="mt-4 grid gap-4 rounded-2xl border border-white/10 bg-slate-900 p-5 lg:mt-8 lg:grid-cols-[minmax(0,1fr)_220px_240px_auto] lg:items-end"
      >
        <label>
          <span className="text-sm text-slate-300">提醒内容</span>
          <input
            {...form.register("title")}
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"
            placeholder="例如：提交项目报告"
          />
          {form.formState.errors.title && (
            <span className="mt-1 block text-sm text-red-300">
              {form.formState.errors.title.message}
            </span>
          )}
        </label>
        <label>
          <span className="text-sm text-slate-300">关联对象（可选）</span>
          <select {...form.register("target_type")} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"><option value="custom">不关联</option><option value="task">任务</option><option value="calendar_event">日程</option></select>
          {form.watch("target_type") !== "custom" && <select {...form.register("target_id")} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"><option value="">请选择</option>{(form.watch("target_type") === "task" ? tasks.data ?? [] : events.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select>}
          {form.formState.errors.target_id && <span className="mt-1 block text-sm text-red-300">{form.formState.errors.target_id.message}</span>}
        </label>
        <label>
          <span className="text-sm text-slate-300">提醒时间（{timezone}）</span>
          <input
            type="datetime-local"
            {...form.register("trigger_at")}
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"
          />
          {form.formState.errors.trigger_at && (
            <span className="mt-1 block text-sm text-red-300">
              {form.formState.errors.trigger_at.message}
            </span>
          )}
        </label>
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="inline-flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-cyan-300 px-5 py-3 text-lg font-semibold text-slate-950 disabled:opacity-50 lg:w-auto lg:rounded-xl lg:text-base"
        >
          <Plus size={18} />
          {createMutation.isPending ? "创建中" : "新建提醒"}
        </button>
        {createMutation.isError && (
          <div role="alert" className="text-sm text-red-300 md:col-span-3">
            创建失败，请检查时间、时区或幂等键后重试。
          </div>
        )}
      </form>

      <div className="mt-8 space-y-3">
        {reminders.isPending && <p className="text-slate-400">正在加载提醒…</p>}
        {reminders.isError && (
          <div role="alert" className="rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-amber-100">
            无法读取提醒，请先通过 Django Session 登录。
          </div>
        )}
        {allReminders.length === 0 && (
          <div className="rounded-2xl border border-dashed border-white/10 p-10 text-center text-slate-500">
            暂无提醒
          </div>
        )}
        {visiblePendingReminders.length > 0 && (
          <ReminderSection title="待发送" count={pendingReminders.length}>
            {visiblePendingReminders.map((reminder) => (
              <ReminderCard
                key={reminder.id}
                reminder={reminder}
                timezone={timezone}
                locale={locale}
                cancelling={cancelMutation.isPending}
                onCancel={(id) => cancelMutation.mutate(id)}
              />
            ))}
            {pendingReminders.length > visiblePendingReminders.length && (
              <button
                type="button"
                onClick={() => setPendingLimit((limit) => limit + PENDING_PAGE_SIZE)}
                className="w-full rounded-xl border border-white/15 px-4 py-3 text-sm text-cyan-200 hover:bg-white/5"
              >
                更多待发送提醒（还有 {pendingReminders.length - visiblePendingReminders.length} 条）
              </button>
            )}
          </ReminderSection>
        )}
        {historicalReminders.length > 0 && (
          <ReminderSection title="提醒记录" count={historicalReminders.length} subtitle="仅显示最近 10 条已发送或已错过提醒">
            {historicalReminders.map((reminder) => (
              <ReminderCard
                key={reminder.id}
                reminder={reminder}
                timezone={timezone}
                locale={locale}
                cancelling={false}
                onCancel={() => undefined}
              />
            ))}
          </ReminderSection>
        )}
      </div>
    </section>
  );
}

function ReminderSection({ title, count, subtitle, children }: { title: string; count: number; subtitle?: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between gap-3 px-1">
        <div><h3 className="text-lg font-semibold text-slate-100">{title}</h3>{subtitle && <p className="mt-1 text-xs text-slate-500">{subtitle}</p>}</div>
        <span className="text-sm text-slate-400">{count} 条</span>
      </div>
      {children}
    </section>
  );
}

function ReminderCard({ reminder, timezone, locale, cancelling, onCancel }: { reminder: Reminder; timezone: string; locale: string; cancelling: boolean; onCancel: (id: string) => void }) {
  const status = reminder.status ?? "pending";
  const canCancel = cancellableStatuses.has(status);
  const automaticOffset = reminder.offset_minutes;
  const offsetLabel = automaticOffset === 0 ? "准点" : automaticOffset === 1440 ? "提前一天" : automaticOffset === 15 ? "提前 15 分钟" : automaticOffset != null ? `提前 ${automaticOffset} 分钟` : "";
  return (
    <article className="rounded-2xl border border-white/10 bg-slate-900 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h4 className="font-medium text-slate-100">{reminder.title}</h4>
          <p className="mt-2 text-sm text-slate-400">{formatInUserTimezone(reminder.trigger_at, timezone, locale)}</p>
          {reminder.target_type !== "custom" && <p className="mt-2 text-xs text-cyan-200">关联{reminder.target_type === "task" ? "任务" : "日程"}{offsetLabel ? ` · ${offsetLabel}` : ""}</p>}
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-3 py-1 text-xs ${statusStyles[status]}`}>{statusLabels[status]}</span>
          {canCancel && <button type="button" aria-label={`取消提醒：${reminder.title}`} disabled={cancelling} onClick={() => onCancel(reminder.id)} className="rounded-lg p-2 text-slate-400 hover:bg-white/5 hover:text-white disabled:opacity-50"><X size={17} /></button>}
        </div>
      </div>
      {(reminder.retry_count ?? 0) > 0 && <p className="mt-3 text-xs text-amber-200">已重试 {reminder.retry_count} 次</p>}
      {reminder.failure_reason && <p className="mt-3 flex items-center gap-2 text-sm text-red-300"><CircleAlert size={16} />{reminder.failure_reason}</p>}
    </article>
  );
}
