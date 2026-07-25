import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarX, Save } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { CalendarEvent } from "../../api/events";
import { Drawer } from "../../components/overlay/drawer";
import { toDateTimeLocalValue, toUtcISOString } from "../../utils/datetime";
import { useCancelEvent, useCreateEvent, useUpdateEvent } from "./hooks";
import { useCreateTask, useTasks } from "../tasks/hooks";

const eventFormSchema = z
  .object({
    title: z.string().trim().min(1, "请输入日程标题").max(255),
    description: z.string().max(5000),
    start_at: z.string().min(1, "请选择开始时间"),
    end_at: z.string().min(1, "请选择结束时间"),
    location: z.string().max(255),
    status: z.enum(["tentative", "confirmed"]),
    visibility: z.enum(["private", "public"]),
    task: z.string(),
    new_task_title: z.string(),
  })
  .refine((values) => values.end_at > values.start_at, {
    message: "结束时间必须晚于开始时间",
    path: ["end_at"],
  })
  .superRefine((values, context) => {
    if (values.task === "__new__" && !values.new_task_title.trim()) {
      context.addIssue({
        code: "custom",
        path: ["new_task_title"],
        message: "请输入新任务标题",
      });
    }
  });

type EventForm = z.infer<typeof eventFormSchema>;

interface EventEditorProps {
  event?: CalendarEvent;
  initialStart?: Date;
  timezone: string;
  defaultDurationMinutes?: number;
  onClose: () => void;
}

function initialValues(
  event: CalendarEvent | undefined,
  initialStart: Date,
  timezone: string,
  defaultDurationMinutes: number,
) {
  const end = new Date(initialStart.getTime() + defaultDurationMinutes * 60 * 1000);
  return {
    title: event?.title ?? "",
    description: event?.description ?? "",
    start_at: toDateTimeLocalValue(event?.start_at ?? initialStart, timezone),
    end_at: toDateTimeLocalValue(event?.end_at ?? end, timezone),
    location: event?.location ?? "",
    status: event?.status === "tentative" ? "tentative" : "confirmed",
    visibility: event?.visibility === "public" ? "public" : "private",
    task: event?.task ?? "",
    new_task_title: "",
  } satisfies EventForm;
}

const inputClass =
  "mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-slate-100 outline-none focus:border-cyan-300/60";

export function EventEditor({
  event,
  initialStart = new Date(),
  timezone,
  defaultDurationMinutes = 60,
  onClose,
}: EventEditorProps) {
  const createMutation = useCreateEvent();
  const updateMutation = useUpdateEvent();
  const cancelMutation = useCancelEvent();
  const [confirmCancel, setConfirmCancel] = useState(false);
  const tasks = useTasks();
  const createTask = useCreateTask();
  const isCancelled = event?.status === "cancelled";
  const form = useForm<EventForm>({
    resolver: zodResolver(eventFormSchema),
    defaultValues: initialValues(event, initialStart, timezone, defaultDurationMinutes),
  });

  const mutationError = createMutation.error ?? updateMutation.error ?? cancelMutation.error ?? createTask.error;
  const onSubmit = form.handleSubmit(async (values) => {
    const taskId = values.task === "__new__"
      ? (await createTask.mutateAsync({
          title: values.new_task_title.trim(),
          planned_start_at: toUtcISOString(values.start_at, timezone),
          planned_end_at: toUtcISOString(values.end_at, timezone),
          source: "local",
          tags: [],
        })).id
      : values.task || null;
    const input = {
      title: values.title.trim(),
      description: values.description.trim(),
      start_at: toUtcISOString(values.start_at, timezone),
      end_at: toUtcISOString(values.end_at, timezone),
      timezone,
      location: values.location.trim(),
      status: values.status,
      visibility: values.visibility,
      task: taskId,
    };
    if (event) {
      updateMutation.mutate(
        { eventId: event.id, expectedVersion: event.version ?? 1, input },
        { onSuccess: onClose },
      );
    } else {
      createMutation.mutate(input, { onSuccess: onClose });
    }
  });

  const cancelEvent = () => {
    if (!event) return;
    cancelMutation.mutate(
      { eventId: event.id, expectedVersion: event.version ?? 1 },
      { onSuccess: onClose },
    );
  };

  return (
    <Drawer
      title={event ? "日程详情" : "创建日程"}
      description={event ? `版本 ${event.version ?? 1} · 来源 ${event.source ?? "local"}` : `时间按 ${timezone} 录入`}
      onClose={onClose}
    >
      {isCancelled && (
        <div className="mb-5 rounded-xl border border-slate-600 bg-slate-800 p-4 text-sm text-slate-300">
          该日程已取消，仅保留历史详情。
        </div>
      )}
      <form onSubmit={onSubmit} className="space-y-5">
        <label className="block text-sm text-slate-300">
          日程标题
          <input {...form.register("title")} disabled={isCancelled} className={inputClass} />
          {form.formState.errors.title && (
            <span className="mt-1 block text-red-300">{form.formState.errors.title.message}</span>
          )}
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm text-slate-300">
            开始时间（{timezone}）
            <input
              type="datetime-local"
              {...form.register("start_at")}
              disabled={isCancelled}
              className={inputClass}
            />
          </label>
          <label className="block text-sm text-slate-300">
            结束时间（{timezone}）
            <input
              type="datetime-local"
              {...form.register("end_at")}
              disabled={isCancelled}
              className={inputClass}
            />
            {form.formState.errors.end_at && (
              <span className="mt-1 block text-red-300">{form.formState.errors.end_at.message}</span>
            )}
          </label>
        </div>
        <label className="block text-sm text-slate-300">
          地点
          <input {...form.register("location")} disabled={isCancelled} className={inputClass} />
        </label>
        <label className="block text-sm text-slate-300">
          关联任务（可选）
          <select {...form.register("task")} disabled={isCancelled} className={inputClass}>
            <option value="">不关联任务</option><option value="__new__">新建任务并关联</option>
            {(tasks.data ?? []).filter((item) => item.status !== "cancelled").map((item) => (
              <option key={item.id} value={item.id}>{item.title}</option>
            ))}
          </select>
          {form.watch("task") === "__new__" && <input {...form.register("new_task_title")} placeholder="新任务标题" className={inputClass} />}
          {form.formState.errors.new_task_title && (
            <span className="mt-1 block text-red-300">{form.formState.errors.new_task_title.message}</span>
          )}
          <span className="mt-2 block text-xs text-slate-500">一个任务可以拥有多条日程；保存后会按日程时间维护提前 1 天、2 小时、30 分钟的提醒。</span>
        </label>
        <label className="block text-sm text-slate-300">
          描述
          <textarea
            {...form.register("description")}
            disabled={isCancelled}
            rows={4}
            className={inputClass}
          />
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm text-slate-300">
            状态
            <select {...form.register("status")} disabled={isCancelled} className={inputClass}>
              <option value="confirmed">已确认</option>
              <option value="tentative">暂定</option>
            </select>
          </label>
          <label className="block text-sm text-slate-300">
            可见性
            <select {...form.register("visibility")} disabled={isCancelled} className={inputClass}>
              <option value="private">私密</option>
              <option value="public">公开</option>
            </select>
            <span className="mt-2 block text-xs text-slate-500">当前仅本人可见；公开/私密为未来共享日历预留，暂不改变访问权限。</span>
          </label>
        </div>
        {mutationError && (
          <div role="alert" className="rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200">
            {mutationError.message}
          </div>
        )}
        {!isCancelled && (
          <div className="flex flex-wrap justify-between gap-3 border-t border-white/10 pt-5">
            {event ? (
              confirmCancel ? (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-amber-200">确定取消？</span>
                  <button
                    type="button"
                    onClick={cancelEvent}
                    className="rounded-lg bg-red-400/15 px-3 py-2 text-sm text-red-200"
                  >
                    确认取消
                  </button>
                  <button type="button" onClick={() => setConfirmCancel(false)} className="px-3 py-2 text-sm text-slate-400">
                    返回
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirmCancel(true)}
                  className="inline-flex items-center gap-2 rounded-xl px-4 py-3 text-red-300 hover:bg-red-400/10"
                >
                  <CalendarX size={18} />
                  取消日程
                </button>
              )
            ) : (
              <span />
            )}
            <button
              type="submit"
              disabled={createMutation.isPending || updateMutation.isPending || createTask.isPending}
              className="inline-flex items-center gap-2 rounded-xl bg-cyan-300 px-5 py-3 font-medium text-slate-950 disabled:opacity-50"
            >
              <Save size={18} />
              {event ? "保存修改" : "创建日程"}
            </button>
          </div>
        )}
      </form>
    </Drawer>
  );
}
