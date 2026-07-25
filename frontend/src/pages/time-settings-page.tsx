import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { updateCurrentUserPreference } from "../api/preferences";
import { getProviderCatalog, searchLocations, type LocationCandidate } from "../api/providers";
import { preferenceQueryKey, useCurrentUserPreference } from "../features/preferences/hooks";
import { getTimezoneLabel } from "../utils/datetime";

const preferenceSchema = z
  .object({
    timezone: z.string().min(1),
    locale: z.enum(["zh-CN", "en-US"]),
    workday_start: z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/),
    workday_end: z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/),
    default_event_duration_minutes: z.coerce.number().int().min(5).max(1440),
    weather_location: z.string().max(255),
    weather_forecast_days: z.coerce.number().int().min(1).max(7),
    news_topics: z.string(),
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
      weather_location: "",
      weather_forecast_days: 3,
      news_topics: "",
    },
  });

  useEffect(() => {
    if (preference.data) {
      form.reset({
        timezone: "Asia/Shanghai",
        locale: preference.data.locale ?? "zh-CN",
        workday_start: preference.data.workday_start?.slice(0, 5) ?? "09:00",
        workday_end: preference.data.workday_end?.slice(0, 5) ?? "18:00",
        default_event_duration_minutes: preference.data.default_event_duration_minutes ?? 60,
        weather_location: preference.data.weather_location ?? "",
        weather_forecast_days: preference.data.weather_forecast_days ?? 3,
        news_topics: Array.isArray(preference.data.news_topics)
          ? preference.data.news_topics.filter((item): item is string => typeof item === "string").join(", ")
          : "",
      });
      setLocationQuery(preference.data.weather_location ?? "");
    }
  }, [form, preference.data]);

  const updatePreference = useMutation({
    mutationFn: updateCurrentUserPreference,
    onSuccess: (data) => {
      queryClient.setQueryData(preferenceQueryKey, data);
    },
  });
  const providerCatalog = useQuery({ queryKey: ["provider-catalog"], queryFn: getProviderCatalog });
  const [locationQuery, setLocationQuery] = useState("");
  const [locationCandidates, setLocationCandidates] = useState<LocationCandidate[]>([]);
  useEffect(() => {
    if (locationQuery.trim().length < 2) { setLocationCandidates([]); return; }
    const timer = window.setTimeout(() => {
      void searchLocations(locationQuery, form.getValues("locale"))
        .then(setLocationCandidates)
        .catch(() => setLocationCandidates([]));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [form, locationQuery]);

  const onSubmit = form.handleSubmit((values) => {
    updatePreference.mutate({
      ...values,
      news_topics: values.news_topics
        .split(/[,，\n]/)
        .map((item) => item.trim())
        .filter(Boolean),
    });
  });
  const timezoneValue = form.watch("timezone") || "Asia/Shanghai";
  const selectedNewsTopics = form.watch("news_topics").split(",").map((item) => item.trim()).filter(Boolean);
  const timezoneLabel = getTimezoneLabel(timezoneValue);
  const useDeviceTimezone = () => {
    const deviceTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const availableTimezones = providerCatalog.data?.timezones ?? ["Asia/Shanghai"];
    if (availableTimezones.includes(deviceTimezone)) {
      form.setValue("timezone", deviceTimezone, { shouldDirty: true });
    }
  };

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
          <select
            {...form.register("timezone")}
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"
          >
            {(providerCatalog.data?.timezones ?? ["Asia/Shanghai"]).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <span className="mt-2 block text-xs text-slate-500">
            {timezoneLabel}
          </span>
          <button
            type="button"
            onClick={useDeviceTimezone}
            className="mt-2 text-xs text-cyan-300 hover:text-cyan-200"
          >
            使用本设备时区
          </button>
          {form.formState.errors.timezone && (
            <span className="text-sm text-red-300">{form.formState.errors.timezone.message}</span>
          )}
        </label>

        <label className="block">
          <span className="text-sm text-slate-300">天气地点</span>
          <input
            value={locationQuery}
            onChange={(event) => setLocationQuery(event.target.value)}
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"
            placeholder="输入城市，如合肥"
          />
          {locationCandidates.length > 0 && <div className="mt-2 overflow-hidden rounded-xl border border-white/10 bg-slate-950">{locationCandidates.map((candidate) => <button key={`${candidate.label}-${candidate.timezone}`} type="button" onClick={() => { form.setValue("weather_location", candidate.label, { shouldDirty: true }); form.setValue("timezone", candidate.timezone, { shouldDirty: true }); setLocationQuery(candidate.label); setLocationCandidates([]); }} className="block w-full px-4 py-3 text-left text-sm hover:bg-white/5">{candidate.label}<span className="ml-2 text-slate-500">{candidate.timezone}</span></button>)}</div>}
          <span className="mt-2 block text-xs text-slate-500">请选择候选城市；选择后会保存标准地点，并可采用该城市时区。</span>
          <input type="hidden" {...form.register("weather_location")} />
        </label>

        <label className="block">
          <span className="text-sm text-slate-300">简报天气天数</span>
          <select {...form.register("weather_forecast_days")} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3">
            {[1, 2, 3, 4, 5, 6, 7].map((days) => <option key={days} value={days}>{days} 天</option>)}
          </select>
        </label>

        <label className="block">
          <span className="text-sm text-slate-300">新闻关注主题</span>
          <div className="mt-2 flex flex-wrap gap-2">{(providerCatalog.data?.news_topics ?? []).map((topic) => <button key={topic} type="button" onClick={() => { const current = form.getValues("news_topics").split(",").map((item) => item.trim()).filter(Boolean); form.setValue("news_topics", current.includes(topic) ? current.filter((item) => item !== topic).join(", ") : [...current, topic].join(", "), { shouldDirty: true }); }} className={`rounded-full border px-3 py-2 text-sm transition ${selectedNewsTopics.includes(topic) ? "border-cyan-300 bg-cyan-300/15 text-cyan-100" : "border-white/10 text-slate-300 hover:border-cyan-300/40"}`}>{topic}</button>)}</div>
          <input type="hidden" {...form.register("news_topics")} />
        </label>

        <div className="rounded-xl border border-white/10 bg-slate-950/60 p-4 text-xs text-slate-400">
          <span className="text-cyan-300">当前新闻来源</span>
          {providerCatalog.data && (
            <div className="mt-3 flex flex-wrap gap-2">
              {providerCatalog.data.news_feeds.map((feed) => (
                <a key={feed.url} href={feed.url} target="_blank" rel="noreferrer" className="rounded-lg bg-white/5 px-2 py-1 text-cyan-200">
                  {feed.name} · {feed.topics.join(" / ")}
                </a>
              ))}
            </div>
          )}
        </div>

        <label className="block">
          <span className="text-sm text-slate-300">语言区域</span>
          <select
            {...form.register("locale")}
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"
          >
            <option value="zh-CN">简体中文</option><option value="en-US">English</option>
          </select>
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
          <span className="mt-2 block text-xs text-slate-500">
            新建日程时，结束时间会按此值自动预填；你仍可在创建前修改，不会改变已有日程或提醒。
          </span>
        </label>

        {updatePreference.isError && (
          <div role="alert" className="rounded-xl bg-red-400/10 p-3 text-sm text-red-200">
            保存失败：{updatePreference.error.message}
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
