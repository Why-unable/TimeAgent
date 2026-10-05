import { zodResolver } from "@hookform/resolvers/zod";
import { Bell, CircleAlert, Plus, X } from "lucide-react";
import type { FormEventHandler, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { useForm, type UseFormReturn } from "react-hook-form";
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
import { Drawer } from "../components/overlay/drawer";
import { formatInUserTimezone, getLocalDateTimeProblem, localDateTimeProblemMessage, toUtcISOString } from "../utils/datetime";

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
  pending: "bg-sky-100 text-sky-900 lg:bg-sky-400/10 lg:text-sky-200",
  queued: "bg-violet-100 text-violet-900 lg:bg-violet-400/10 lg:text-violet-200",
  sending: "bg-amber-100 text-amber-900 lg:bg-amber-400/10 lg:text-amber-200",
  sent: "bg-emerald-100 text-emerald-900 lg:bg-emerald-400/10 lg:text-emerald-200",
  failed: "bg-red-100 text-red-900 lg:bg-red-400/10 lg:text-red-200",
  cancelled: "bg-slate-100 text-slate-700 lg:bg-slate-400/10 lg:text-slate-300",
  missed: "bg-orange-100 text-orange-900 lg:bg-orange-400/10 lg:text-orange-200",
};

const cancellableStatuses = new Set<Reminder["status"]>(["pending", "queued", "failed"]);
const pendingStatuses = new Set<Reminder["status"]>(["pending", "queued", "sending"]);
const SENT_HISTORY_LIMIT = 10;
const PENDING_PAGE_SIZE = 10;

export function RemindersPage() {
  const preference = useCurrentUserPreference();
  const reminders = useReminders();
  const createMutation = useCreateReminder();
  const cancelMutation = useCancelReminder();
  const idempotencyKey = useRef(crypto.randomUUID());
  const [isMobileViewport, setIsMobileViewport] = useState(() => window.innerWidth < 1024);
  const [createOpen, setCreateOpen] = useState(false);
  const [createdNotice, setCreatedNotice] = useState("");
  const [cancelRetryId, setCancelRetryId] = useState<string | null>(null);
  const timezone = preference.data?.timezone ?? "Asia/Shanghai";
  const locale = preference.data?.locale ?? "zh-CN";
  const tasks = useTasks();
  const events = useEvents({});
  const form = useForm<ReminderForm>({
    resolver: zodResolver(reminderFormSchema),
    defaultValues: { title: "", trigger_at: "", target_type: "custom", target_id: "" },
  });

  useEffect(() => {
    const updateViewport = () => setIsMobileViewport(window.innerWidth < 1024);
    window.addEventListener("resize", updateViewport);
    return () => window.removeEventListener("resize", updateViewport);
  }, []);

  const [pendingLimit, setPendingLimit] = useState(PENDING_PAGE_SIZE);
  const allReminders = reminders.data ?? [];
  const failedReminders = allReminders.filter((item) => item.status === "failed");
  const cancelledReminders = allReminders.filter((item) => item.status === "cancelled");
  const pendingReminders = allReminders.filter((item) => pendingStatuses.has(item.status));
  const historicalReminders = allReminders
    .filter((item) => item.status === "sent" || item.status === "missed")
    .slice()
    .sort((left, right) => Date.parse(right.sent_at ?? right.updated_at) - Date.parse(left.sent_at ?? left.updated_at))
    .slice(0, SENT_HISTORY_LIMIT);
  const visiblePendingReminders = pendingReminders.slice(0, pendingLimit);

  const onSubmit = form.handleSubmit((values) => {
    const problem = getLocalDateTimeProblem(values.trigger_at, timezone);
    if (problem) {
      form.setError("trigger_at", { type: "validate", message: localDateTimeProblemMessage(problem, timezone) });
      form.setFocus("trigger_at");
      return;
    }
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
          setCreatedNotice("提醒已创建。定时发送状态会显示在提醒列表中。");
          setCreateOpen(false);
        },
      },
    );
  });

  const cancelReminderById = (id: string) => {
    setCancelRetryId(id);
    cancelMutation.reset();
    cancelMutation.mutate(id, { onSuccess: () => setCancelRetryId(null) });
  };

  const createErrorMessage = createMutation.error instanceof Error
    ? createMutation.error.message
    : "创建失败，请检查提醒内容和时间后重试。";

  return (
    <section className="mx-auto max-w-5xl">
      <ScheduleWorkspaceTabs />
      {/* Desktop heading */}
      <div className="mt-2 hidden items-center gap-3 lg:flex">
        <Bell className="text-cyan-300" />
        <h1 className="text-3xl font-semibold">提醒</h1>
      </div>
      <header className="mt-4 flex items-center justify-between gap-3 lg:hidden">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">提醒</h1>
          <p className="mt-1 text-sm text-slate-600">时间按 {timezone} 显示。</p>
        </div>
        <button
          type="button"
          aria-label="打开新建提醒"
          onClick={() => {
            createMutation.reset();
            form.clearErrors();
            setCreatedNotice("");
            setCreateOpen(true);
          }}
          className="inline-flex min-h-12 shrink-0 items-center gap-2 rounded-xl bg-teal-700 px-4 text-sm font-semibold text-white mobile-on-brand"
        >
          <Plus size={18} aria-hidden="true" /> 新建提醒
        </button>
      </header>
      {!isMobileViewport && (
        <ReminderCreateForm
          form={form}
          timezone={timezone}
          tasks={tasks.data ?? []}
          events={events.data ?? []}
          pending={createMutation.isPending}
          error={createMutation.isError ? createErrorMessage : ""}
          onSubmit={onSubmit}
          mobile={false}
        />
      )}
      {isMobileViewport && createOpen && (
        <Drawer
          title="新建提醒"
          description={`填写内容和时间；时间按 ${timezone} 解释。`}
          onClose={() => setCreateOpen(false)}
        >
          <ReminderCreateForm
            form={form}
            timezone={timezone}
            tasks={tasks.data ?? []}
            events={events.data ?? []}
            pending={createMutation.isPending}
            error={createMutation.isError ? createErrorMessage : ""}
            onSubmit={onSubmit}
            mobile
          />
        </Drawer>
      )}
      {createdNotice && <p role="status" className="mt-3 text-sm text-emerald-800">{createdNotice}</p>}

      <div className="mt-8 space-y-3">
        {reminders.isPending && <p role="status" className="text-sm text-slate-600">正在加载提醒…</p>}
        {reminders.isError && (
          <div role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-950">
            <p>暂时无法读取提醒，请检查连接后重试。</p>
            <button type="button" onClick={() => void reminders.refetch()} className="mt-2 inline-flex min-h-11 items-center underline underline-offset-2">重试读取</button>
          </div>
        )}
        {cancelMutation.isError && cancelRetryId && (
          <div role="alert" className="rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-950">
            <p>取消提醒失败。它仍保留在列表中，你可以重试。</p>
            <button type="button" onClick={() => cancelReminderById(cancelRetryId)} className="mt-2 inline-flex min-h-11 items-center underline underline-offset-2">重试取消</button>
          </div>
        )}
        {reminders.isSuccess && allReminders.length === 0 && <p className="border-b border-slate-200 py-6 text-sm text-slate-600">还没有提醒。新建一条后，发送状态会显示在这里。</p>}
        {reminders.isSuccess && allReminders.length > 0 && failedReminders.length === 0 && pendingReminders.length === 0 && historicalReminders.length === 0 && cancelledReminders.length === 0 && <p className="border-b border-slate-200 py-6 text-sm text-slate-600">当前没有可显示的提醒记录。</p>}
        {failedReminders.length > 0 && (
          <ReminderSection title="需要处理" count={failedReminders.length} subtitle="发送失败；可取消后重新创建">
            {failedReminders.map((reminder) => <ReminderCard key={reminder.id} reminder={reminder} timezone={timezone} locale={locale} cancelling={cancelMutation.isPending} onCancel={cancelReminderById} />)}
          </ReminderSection>
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
                onCancel={cancelReminderById}
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
        {cancelledReminders.length > 0 && (
          <details className="border-b border-slate-200 py-2">
            <summary className="flex min-h-12 cursor-pointer items-center justify-between text-sm font-medium text-slate-700">
              <span>已取消</span><span className="text-slate-500">{cancelledReminders.length} 条</span>
            </summary>
            <div className="mt-2"><ReminderSection title="已取消的提醒" count={cancelledReminders.length}>
              {cancelledReminders.slice(0, SENT_HISTORY_LIMIT).map((reminder) => <ReminderCard key={reminder.id} reminder={reminder} timezone={timezone} locale={locale} cancelling={false} onCancel={() => undefined} />)}
            </ReminderSection></div>
          </details>
        )}
      </div>
    </section>
  );
}

function ReminderSection({ title, count, subtitle, children }: { title: string; count: number; subtitle?: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between gap-3 px-1">
        <div><h2 className="text-lg font-semibold text-slate-100">{title}</h2>{subtitle && <p className="mt-1 text-xs text-slate-500">{subtitle}</p>}</div>
        <span className="text-sm text-slate-400">{count} 条</span>
      </div>
      {children}
    </section>
  );
}

function ReminderCreateForm({
  form,
  timezone,
  tasks,
  events,
  pending,
  error,
  onSubmit,
  mobile,
}: {
  form: UseFormReturn<ReminderForm>;
  timezone: string;
  tasks: Array<{ id: string; title: string }>;
  events: Array<{ id: string; title: string }>;
  pending: boolean;
  error: string;
  onSubmit: FormEventHandler<HTMLFormElement>;
  mobile: boolean;
}) {
  const targetType = form.watch("target_type");
  const options = targetType === "task" ? tasks : events;
  const inputClass = "mt-2 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base text-slate-900 outline-none focus-visible:ring-2 focus-visible:ring-teal-700";
  return (
    <form onSubmit={onSubmit} className={mobile ? "grid gap-5" : "mt-8 grid gap-4 rounded-2xl border border-white/10 bg-slate-900 p-5 lg:grid-cols-[minmax(0,1fr)_220px_240px_auto] lg:items-end"}>
      <label htmlFor="reminder-title" className="block text-sm font-medium text-slate-700">
        提醒内容
        <input id="reminder-title" aria-invalid={Boolean(form.formState.errors.title)} aria-describedby={form.formState.errors.title ? "reminder-title-error" : undefined} {...form.register("title")} className={inputClass} placeholder="例如：提交项目报告" />
        {form.formState.errors.title && <span id="reminder-title-error" className="mt-1 block text-sm text-red-800">{form.formState.errors.title.message}</span>}
      </label>
      <label htmlFor="reminder-time" className="block text-sm font-medium text-slate-700">
        提醒时间（{timezone}）
        <input id="reminder-time" type="datetime-local" aria-invalid={Boolean(form.formState.errors.trigger_at)} aria-describedby={form.formState.errors.trigger_at ? "reminder-time-error" : undefined} {...form.register("trigger_at")} className={inputClass} />
        {form.formState.errors.trigger_at && <span id="reminder-time-error" className="mt-1 block text-sm text-red-800">{form.formState.errors.trigger_at.message}</span>}
      </label>
      <fieldset className="min-w-0">
        <legend className="text-sm font-medium text-slate-700">关联对象（可选）</legend>
        <label htmlFor="reminder-target-type" className="sr-only">关联对象类型</label>
        <select id="reminder-target-type" {...form.register("target_type")} className={inputClass}>
          <option value="custom">不关联</option><option value="task">任务</option><option value="calendar_event">日程</option>
        </select>
        {targetType !== "custom" && <>
          <label htmlFor="reminder-target-id" className="sr-only">选择关联的{targetType === "task" ? "任务" : "日程"}</label>
          <select id="reminder-target-id" aria-invalid={Boolean(form.formState.errors.target_id)} aria-describedby={form.formState.errors.target_id ? "reminder-target-error" : undefined} {...form.register("target_id")} className={inputClass}>
            <option value="">请选择</option>{options.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
        </>}
        {form.formState.errors.target_id && <span id="reminder-target-error" className="mt-1 block text-sm text-red-800">{form.formState.errors.target_id.message}</span>}
      </fieldset>
      {error && <p role="alert" className="text-sm text-red-800">创建失败：{error}</p>}
      <button type="submit" disabled={pending} className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-teal-700 px-5 text-base font-semibold text-white disabled:opacity-50 lg:w-auto">
        <Plus size={18} aria-hidden="true" />{pending ? "创建中…" : mobile ? "创建提醒" : "新建提醒"}
      </button>
    </form>
  );
}

function ReminderCard({ reminder, timezone, locale, cancelling, onCancel }: { reminder: Reminder; timezone: string; locale: string; cancelling: boolean; onCancel: (id: string) => void }) {
  const status = reminder.status ?? "pending";
  const canCancel = cancellableStatuses.has(status);
  const automaticOffset = reminder.offset_minutes;
  const offsetLabel = automaticOffset === 0 ? "准点" : automaticOffset === 1440 ? "提前一天" : automaticOffset === 15 ? "提前 15 分钟" : automaticOffset != null ? `提前 ${automaticOffset} 分钟` : "";
  return (
    <article data-surface="divider-list" className="reminder-list-row border-b border-slate-200 py-4 last:border-b-0 lg:rounded-2xl lg:border lg:border-white/10 lg:p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="font-medium text-slate-100">{reminder.title}</h3>
          <p className="mt-2 text-sm text-slate-400">{formatInUserTimezone(reminder.trigger_at, timezone, locale)}</p>
          {reminder.target_type !== "custom" && <p className="mt-2 text-xs text-cyan-200">关联{reminder.target_type === "task" ? "任务" : "日程"}{offsetLabel ? ` · ${offsetLabel}` : ""}</p>}
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-3 py-1 text-xs ${statusStyles[status]}`}>{statusLabels[status]}</span>
          {canCancel && <button type="button" aria-label={`取消提醒：${reminder.title}`} disabled={cancelling} onClick={() => onCancel(reminder.id)} className="inline-flex min-h-11 min-w-11 items-center justify-center gap-1 rounded-lg px-2 text-sm text-red-800 hover:bg-red-50 disabled:opacity-50"><X size={17} aria-hidden="true" /><span className="sr-only">取消</span></button>}
        </div>
      </div>
      {(reminder.retry_count ?? 0) > 0 && <p className="mt-3 text-xs text-amber-200">已重试 {reminder.retry_count} 次</p>}
      {reminder.failure_reason && <p className="mt-3 flex items-center gap-2 text-sm text-red-300"><CircleAlert size={16} />{reminder.failure_reason}</p>}
    </article>
  );
}
