type StatusCardProps = {
  label: string;
  ok: boolean;
  loading?: boolean;
  detail?: string;
};

export function StatusCard({ label, ok, loading = false, detail }: StatusCardProps) {
  const text = loading ? "检查中" : ok ? "正常" : "异常";

  return (
    <article className="rounded-2xl border border-white/10 bg-slate-900 p-5 shadow-xl shadow-black/10">
      <div className="flex items-center justify-between gap-4">
        <h3 className="font-medium text-slate-200">{label}</h3>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-medium ${
            loading
              ? "bg-amber-400/15 text-amber-200"
              : ok
                ? "bg-emerald-400/15 text-emerald-200"
                : "bg-red-400/15 text-red-200"
          }`}
        >
          {text}
        </span>
      </div>
      <p className="mt-6 text-sm text-slate-400">{detail ?? `服务状态：${text}`}</p>
    </article>
  );
}

