export function PlaceholderPage({ title }: { title: string }) {
  return (
    <section className="mx-auto max-w-4xl">
      <p className="text-sm font-medium text-cyan-300">后续阶段</p>
      <h2 className="mt-2 text-3xl font-semibold">{title}</h2>
      <p className="mt-4 text-slate-400">该业务页面尚未实现，目前仅保留路由入口。</p>
    </section>
  );
}

