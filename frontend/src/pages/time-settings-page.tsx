import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { updateCurrentUserPreference } from "../api/preferences";
import {
  getAdministrativeAreas,
  getProviderCatalog,
  resolveAdministrativeLocation,
  resolveCurrentLocation,
  type AdministrativeAreaOption,
  type LocationCandidate,
} from "../api/providers";
import { preferenceQueryKey, useCurrentUserPreference } from "../features/preferences/hooks";
import { getCurrentDeviceCoordinates } from "../native/geolocation";
import { getTimezoneLabel } from "../utils/datetime";

const preferenceSchema = z
  .object({
    timezone: z.string().min(1),
    locale: z.enum(["zh-CN", "en-US"]),
    workday_start: z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/),
    workday_end: z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/),
    default_event_duration_minutes: z.coerce.number().int().min(5).max(1440),
    weather_location: z.string().max(255),
    weather_location_data: z.record(z.string(), z.unknown()),
    weather_forecast_days: z.coerce.number().int().min(1).max(7),
    require_event_creation_approval: z.boolean(),
    require_event_cancellation_approval: z.boolean(),
    news_topics: z.string(),
  })
  .refine((value) => value.workday_start < value.workday_end, {
    message: "工作结束时间必须晚于开始时间",
    path: ["workday_end"],
  });

type PreferenceForm = z.infer<typeof preferenceSchema>;
const EMPTY_ADMINISTRATIVE_OPTIONS: readonly AdministrativeAreaOption[] = [];

function messageForLocationError(error: unknown): string {
  if (error instanceof Error && /permission/i.test(error.message)) return "未获得位置权限，请在系统设置中允许位置访问。";
  if (error instanceof Error && /timeout|time/i.test(error.message)) return "定位超时，请到开阔处重试，或手动选择省、市、区。";
  return "无法获取完整的省、市、区位置，请重试或手动选择。";
}

function administrativeParts(value: unknown) {
  if (!value || typeof value !== "object") return undefined;
  const data = value as Record<string, unknown>;
  return typeof data.province === "string" && typeof data.city === "string" && typeof data.district === "string"
    ? { province: data.province, city: data.city, district: data.district }
    : undefined;
}

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
      weather_location_data: {},
      weather_forecast_days: 3,
      require_event_creation_approval: false,
      require_event_cancellation_approval: false,
      news_topics: "",
    },
  });
  const [provinceCode, setProvinceCode] = useState("");
  const [cityCode, setCityCode] = useState("");
  const [districtCode, setDistrictCode] = useState("");
  const [savedAdministrativeParts, setSavedAdministrativeParts] = useState<{
    province: string;
    city: string;
    district: string;
  }>();
  const [locationError, setLocationError] = useState<string | null>(null);
  const [isResolvingLocation, setIsResolvingLocation] = useState(false);

  const provincesQuery = useQuery({ queryKey: ["administrative-areas"], queryFn: () => getAdministrativeAreas(), staleTime: Infinity });
  const citiesQuery = useQuery({ queryKey: ["administrative-areas", provinceCode], queryFn: () => getAdministrativeAreas(provinceCode), enabled: Boolean(provinceCode), staleTime: Infinity });
  const districtsQuery = useQuery({ queryKey: ["administrative-areas", provinceCode, cityCode], queryFn: () => getAdministrativeAreas("", cityCode), enabled: Boolean(cityCode), staleTime: Infinity });
  const provinces = provincesQuery.data ?? EMPTY_ADMINISTRATIVE_OPTIONS;
  const cities = citiesQuery.data ?? EMPTY_ADMINISTRATIVE_OPTIONS;
  const districts = districtsQuery.data ?? EMPTY_ADMINISTRATIVE_OPTIONS;
  const province = provinces.find((option) => option.code === provinceCode);
  const city = cities.find((option) => option.code === cityCode);

  useEffect(() => {
    if (!preference.data) return;
    form.reset({
      timezone: "Asia/Shanghai",
      locale: preference.data.locale ?? "zh-CN",
      workday_start: preference.data.workday_start?.slice(0, 5) ?? "09:00",
      workday_end: preference.data.workday_end?.slice(0, 5) ?? "18:00",
      default_event_duration_minutes: preference.data.default_event_duration_minutes ?? 60,
      weather_location: preference.data.weather_location ?? "",
      weather_location_data: preference.data.weather_location_data ?? {},
      weather_forecast_days: preference.data.weather_forecast_days ?? 3,
      require_event_creation_approval: preference.data.require_event_creation_approval ?? false,
      require_event_cancellation_approval: preference.data.require_event_cancellation_approval ?? false,
      news_topics: Array.isArray(preference.data.news_topics)
        ? preference.data.news_topics.filter((item): item is string => typeof item === "string").join(", ")
        : "",
    });
    setSavedAdministrativeParts(administrativeParts(preference.data.weather_location_data));
  }, [form, preference.data]);

  useEffect(() => {
    if (!savedAdministrativeParts || provinceCode || !provinces.length) return;
    const selected = provinces.find((option) => option.name === savedAdministrativeParts.province);
    if (selected) setProvinceCode(selected.code);
  }, [provinceCode, provinces, savedAdministrativeParts]);

  useEffect(() => {
    if (!savedAdministrativeParts || cityCode || !cities.length) return;
    const selected = cities.find((option) => option.name === savedAdministrativeParts.city);
    if (selected) setCityCode(selected.code);
  }, [cities, cityCode, savedAdministrativeParts]);

  useEffect(() => {
    if (!savedAdministrativeParts || districtCode || !districts.length) return;
    const selected = districts.find((option) => option.name === savedAdministrativeParts.district);
    if (selected) setDistrictCode(selected.code);
  }, [districtCode, districts, savedAdministrativeParts]);

  const updatePreference = useMutation({
    mutationFn: updateCurrentUserPreference,
    onSuccess: (data) => queryClient.setQueryData(preferenceQueryKey, data),
  });
  const providerCatalog = useQuery({ queryKey: ["provider-catalog"], queryFn: getProviderCatalog });

  const applyLocation = (candidate: LocationCandidate) => {
    form.setValue("weather_location", candidate.label, { shouldDirty: true });
    form.setValue("weather_location_data", { ...candidate }, { shouldDirty: true });
    setLocationError(null);
  };

  const resolveSelectedLocation = async (nextProvince: string, nextCity: string, nextDistrict: string) => {
    setIsResolvingLocation(true);
    setLocationError(null);
    try {
      applyLocation(await resolveAdministrativeLocation(nextProvince, nextCity, nextDistrict, form.getValues("locale")));
    } catch (error) {
      form.setValue("weather_location", "", { shouldDirty: true });
      form.setValue("weather_location_data", {}, { shouldDirty: true });
      setLocationError(messageForLocationError(error));
    } finally {
      setIsResolvingLocation(false);
    }
  };

  const handleUseCurrentLocation = async () => {
    setLocationError(null);
    setIsResolvingLocation(true);
    try {
      const coordinates = await getCurrentDeviceCoordinates();
      const candidate = await resolveCurrentLocation(
        coordinates.latitude,
        coordinates.longitude,
        Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai",
        form.getValues("locale"),
      );
      const selectedProvince = provinces.find((option) => option.name === candidate.province);
      const selectedCities = selectedProvince
        ? await queryClient.fetchQuery({
            queryKey: ["administrative-areas", selectedProvince.code],
            queryFn: () => getAdministrativeAreas(selectedProvince.code),
            staleTime: Infinity,
          })
        : [];
      const selectedCity = selectedCities.find((option) => option.name === candidate.city);
      const selectedDistricts = selectedCity
        ? await queryClient.fetchQuery({
            queryKey: ["administrative-areas", selectedProvince?.code, selectedCity.code],
            queryFn: () => getAdministrativeAreas("", selectedCity.code),
            staleTime: Infinity,
          })
        : [];
      const selectedDistrict = selectedDistricts.find((option) => option.name === candidate.district);
      if (!selectedProvince || !selectedCity || !selectedDistrict) {
        throw new Error("The current location is outside the supported administrative directory");
      }
      setProvinceCode(selectedProvince.code);
      setCityCode(selectedCity.code);
      setDistrictCode(selectedDistrict.code);
      applyLocation(candidate);
    } catch (error) {
      setLocationError(messageForLocationError(error));
    } finally {
      setIsResolvingLocation(false);
    }
  };

  const onSubmit = form.handleSubmit((values) => {
    updatePreference.mutate({
      ...values,
      news_topics: values.news_topics.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean),
    });
  });
  const timezoneValue = form.watch("timezone") || "Asia/Shanghai";
  const selectedNewsTopics = form.watch("news_topics").split(",").map((item) => item.trim()).filter(Boolean);
  const useDeviceTimezone = () => {
    const deviceTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if ((providerCatalog.data?.timezones ?? ["Asia/Shanghai"]).includes(deviceTimezone)) {
      form.setValue("timezone", deviceTimezone, { shouldDirty: true });
    }
  };

  if (preference.isError) {
    return <section className="mx-auto max-w-3xl"><h2 className="text-3xl font-semibold">偏好设置</h2><div role="alert" className="mt-6 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-amber-100">请先登录，再读取或修改个人偏好。</div></section>;
  }

  return (
    <section className="mx-auto max-w-3xl">
      <h2 className="mt-2 text-3xl font-semibold">偏好设置</h2>
      <p className="mt-3 text-slate-400">后端保存 IANA 时区，并负责最终时区和工作时间校验。</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-6 rounded-2xl border border-white/10 bg-slate-900 p-6">
        <label className="block"><span className="text-sm text-slate-300">IANA 时区</span><select {...form.register("timezone")} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3">{(providerCatalog.data?.timezones ?? ["Asia/Shanghai"]).map((item) => <option key={item} value={item}>{item}</option>)}</select><span className="mt-2 block text-xs text-slate-500">{getTimezoneLabel(timezoneValue)}</span><button type="button" onClick={useDeviceTimezone} className="mt-2 text-xs text-cyan-300 hover:text-cyan-200">使用本设备时区</button></label>

        <fieldset className="rounded-xl border border-white/10 bg-slate-950/40 p-4">
          <legend className="px-1 text-sm font-medium text-slate-200">天气地点</legend>
          <p className="mb-4 text-xs text-slate-500">按省、市、区选择；不会接受自由输入。选择完成后系统会保存经纬度。</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block text-sm text-slate-300">省<select value={provinceCode} onChange={(event) => { setLocationError(null); setProvinceCode(event.target.value); setCityCode(""); setDistrictCode(""); form.setValue("weather_location", "", { shouldDirty: true }); form.setValue("weather_location_data", {}, { shouldDirty: true }); }} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-3"><option value="">请选择省</option>{provinces.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
            <label className="block text-sm text-slate-300">市<select value={cityCode} disabled={!provinceCode} onChange={(event) => { setLocationError(null); setCityCode(event.target.value); setDistrictCode(""); form.setValue("weather_location", "", { shouldDirty: true }); form.setValue("weather_location_data", {}, { shouldDirty: true }); }} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-3 disabled:opacity-50"><option value="">请选择市</option>{cities.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
            <label className="block text-sm text-slate-300">区 / 县<select value={districtCode} disabled={!cityCode} onChange={(event) => { const nextDistrict = districts.find((item) => item.code === event.target.value); setLocationError(null); setDistrictCode(event.target.value); if (province && city && nextDistrict) void resolveSelectedLocation(province.name, city.name, nextDistrict.name); }} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-3 disabled:opacity-50"><option value="">请选择区 / 县</option>{districts.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
          </div>
          <button type="button" onClick={() => void handleUseCurrentLocation()} disabled={isResolvingLocation} className="mt-4 text-sm text-cyan-300 hover:text-cyan-200 disabled:opacity-50">{isResolvingLocation ? "正在定位与解析…" : "使用当前位置"}</button>
          {form.watch("weather_location") && <p className="mt-3 text-sm text-slate-300">已选：{form.watch("weather_location")}</p>}
          {locationError && <span role="alert" className="mt-2 block text-xs text-red-300">{locationError}</span>}
          <input type="hidden" {...form.register("weather_location")} />
        </fieldset>

        <label className="block"><span className="text-sm text-slate-300">简报天气天数</span><select {...form.register("weather_forecast_days")} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3">{[1, 2, 3, 4, 5, 6, 7].map((days) => <option key={days} value={days}>{days} 天</option>)}</select></label>
        <fieldset className="rounded-xl border border-white/10 bg-slate-950/40 p-4"><legend className="px-1 text-sm font-medium text-slate-200">聊天操作确认</legend><label className="mt-3 flex cursor-pointer items-start gap-3 text-sm text-slate-300"><input type="checkbox" {...form.register("require_event_creation_approval")} className="mt-1 size-4 accent-cyan-400" /><span><span className="block font-medium text-slate-100">创建日程时要求确认</span><span className="mt-1 block text-xs text-slate-500">默认关闭；无冲突日程直接创建，出现冲突时仍必须确认。</span></span></label><label className="mt-4 flex cursor-pointer items-start gap-3 text-sm text-slate-300"><input type="checkbox" {...form.register("require_event_cancellation_approval")} className="mt-1 size-4 accent-cyan-400" /><span><span className="block font-medium text-slate-100">取消日程时要求确认</span><span className="mt-1 block text-xs text-slate-500">默认关闭；聊天助手可直接取消你明确指定的日程。</span></span></label></fieldset>
        <label className="block"><span className="text-sm text-slate-300">新闻关注主题</span><div className="mt-2 flex flex-wrap gap-2">{(providerCatalog.data?.news_topics ?? []).map((topic) => <button key={topic} type="button" onClick={() => { const current = form.getValues("news_topics").split(",").map((item) => item.trim()).filter(Boolean); form.setValue("news_topics", current.includes(topic) ? current.filter((item) => item !== topic).join(", ") : [...current, topic].join(", "), { shouldDirty: true }); }} className={`rounded-full border px-3 py-2 text-sm transition ${selectedNewsTopics.includes(topic) ? "border-cyan-300 bg-cyan-300/15 text-cyan-100" : "border-white/10 text-slate-300 hover:border-cyan-300/40"}`}>{topic}</button>)}</div><input type="hidden" {...form.register("news_topics")} /></label>
        <label className="block"><span className="text-sm text-slate-300">语言区域</span><select {...form.register("locale")} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3"><option value="zh-CN">简体中文</option><option value="en-US">English</option></select></label>
        <div className="grid gap-4 sm:grid-cols-2"><label><span className="text-sm text-slate-300">工作开始</span><input type="time" {...form.register("workday_start")} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3" /></label><label><span className="text-sm text-slate-300">工作结束</span><input type="time" {...form.register("workday_end")} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3" />{form.formState.errors.workday_end && <span className="text-sm text-red-300">{form.formState.errors.workday_end.message}</span>}</label></div>
        <label className="block"><span className="text-sm text-slate-300">默认事件时长（分钟）</span><input type="number" {...form.register("default_event_duration_minutes")} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3" /></label>
        {updatePreference.isError && <div role="alert" className="rounded-xl bg-red-400/10 p-3 text-sm text-red-200">保存失败：{updatePreference.error.message}</div>}
        {updatePreference.isSuccess && <div role="status" className="rounded-xl bg-emerald-400/10 p-3 text-sm text-emerald-200">偏好已保存。</div>}
        <button type="submit" disabled={updatePreference.isPending || isResolvingLocation} className="rounded-xl bg-cyan-300 px-5 py-3 font-medium text-slate-950 disabled:opacity-50">{updatePreference.isPending ? "保存中…" : "保存偏好"}</button>
      </form>
    </section>
  );
}
