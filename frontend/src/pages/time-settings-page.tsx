import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { updateCurrentUserPreference } from "../api/preferences";
import { preferenceQueryKey, useCurrentUserPreference } from "../features/preferences/hooks";
import { getTimezoneLabel } from "../utils/datetime";

const preferenceSchema = z
  .object({
    timezone: z.string().min(1),
    locale: z.string().min(2).max(35),
    workday_start: z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/),
    workday_end: z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/),
    default_event_duration_minutes: z.coerce.number().int().min(5).max(1440),
  })
  .refine((value) => value.workday_start < value.workday_end, {
    message: "工作结束时间必须晚于开始时间",
    path: ["workday_end"],
  });

type PreferenceForm = z.infer<typeof preferenceSchema>;

export function TimeSettingsPage() {
  const queryClient = useQueryClient();
  const preference = useCurrentUserPreference();
  const form = useForm<PreferenceForm>({
    resolver: zodResolver(preferenceSchema),
    defaultValues: {
      timezone: import.meta.env.VITE_DEFAULT_TIMEZONE ?? "Asia/Shanghai",
      locale: "zh-CN",
      workday_start: "09:00",
      workday_end: "18:00",
      default_event_duration_minutes: 60,
    },
  });

  useEffect(() => {
    if (preference.data) {
      form.reset({
        timezone: preference.data.timezone ?? "Asia/Shanghai",
        locale: preference.data.locale ?? "zh-CN",
        workday_start: preference.data.workday_start?.slice(0, 5) ?? "09:00",
        workday_end: preference.data.workday_end?.slice(0, 5) ?? "18:00",
        default_event_duration_minutes: preference.data.default_event_duration_minutes ?? 60,
      });
    }
  }, [form, preference.data]);

  const updatePreference = useMutation({
    mutationFn: updateCurrentUserPreference,
    onSuccess: (data) => {
      queryClient.setQueryData(preferenceQueryKey, data);
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    updatePreference.mutate(values);
  });
  const timezoneValue = form.watch("timezone") || "Asia/Shanghai";
  let timezoneLabel = "请输入有效的 IANA 时区";
  try {
    timezoneLabel = getTimezoneLabel(timezoneValue);
  } catch {
    // The backend remains the authority for timezone validation.
  }

  if (preference.isError) {
    return (
      <section className="mx-auto max-w-3xl">
        <h2 className="text-3xl font-semibold">时间偏好</h2>
        <div role="alert" className="mt-6 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-amber-100">
          请先通过 Django Session 登录，再读取或修改个人时间偏好。
        </div>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-3xl">
      <p className="text-sm font-medium text-cyan-300">Phase 1 · 时间基础</p>
      <h2 className="mt-2 text-3xl font-semibold">时间偏好</h2>
      <p className="mt-3 text-slate-400">
        后端保存 IANA 时区，并负责最终时区和工作时间校验。
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-6 rounded-2xl border border-white/10 bg-slate-900 p-6">
        <label className="block">
          <span className="text-sm text-slate-300">IANA 时区</span>
          <input
            {...form.register("timezone")}
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"
            placeholder="Asia/Shanghai"
          />
          <span className="mt-2 block text-xs text-slate-500">
            {timezoneLabel}
          </span>
          {form.formState.errors.timezone && (
            <span className="text-sm text-red-300">{form.formState.errors.timezone.message}</span>
          )}
        </label>

        <label className="block">
          <span className="text-sm text-slate-300">语言区域</span>
          <input
            {...form.register("locale")}
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"
            placeholder="zh-CN"
          />
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          <label>
            <span className="text-sm text-slate-300">工作开始</span>
            <input
              type="time"
              {...form.register("workday_start")}
              className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"
            />
          </label>
          <label>
            <span className="text-sm text-slate-300">工作结束</span>
            <input
              type="time"
              {...form.register("workday_end")}
              className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"
            />
            {form.formState.errors.workday_end && (
              <span className="text-sm text-red-300">
                {form.formState.errors.workday_end.message}
              </span>
            )}
          </label>
        </div>

        <label className="block">
          <span className="text-sm text-slate-300">默认事件时长（分钟）</span>
          <input
            type="number"
            {...form.register("default_event_duration_minutes")}
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"
          />
        </label>

        {updatePreference.isError && (
          <div role="alert" className="rounded-xl bg-red-400/10 p-3 text-sm text-red-200">
            保存失败，请检查时区和工作时间设置。
          </div>
        )}
        {updatePreference.isSuccess && (
          <div role="status" className="rounded-xl bg-emerald-400/10 p-3 text-sm text-emerald-200">
            时间偏好已保存。
          </div>
        )}

        <button
          type="submit"
          disabled={updatePreference.isPending}
          className="rounded-xl bg-cyan-300 px-5 py-3 font-medium text-slate-950 disabled:opacity-50"
        >
          {updatePreference.isPending ? "保存中…" : "保存偏好"}
        </button>
      </form>
    </section>
  );
}
