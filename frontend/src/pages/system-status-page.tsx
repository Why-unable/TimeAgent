import { useQuery } from "@tanstack/react-query";

import { getReadiness } from "../api/health";
import { StatusCard } from "../components/status/status-card";

export function SystemStatusPage() {
  const readiness = useQuery({
    queryKey: ["health", "ready"],
    queryFn: getReadiness,
    refetchInterval: 30_000,
  });

  const djangoOk = readiness.isSuccess;
  const databaseOk = readiness.data?.checks.database === "ok";
  const redisOk = readiness.data?.checks.redis === "ok";

  return (
    <section className="mx-auto max-w-5xl">
      <p className="text-sm font-medium text-cyan-300">Phase 0 · 工程骨架</p>
      <h2 className="mt-2 text-3xl font-semibold tracking-tight">系统状态</h2>
      <p className="mt-3 max-w-2xl text-slate-400">
        此页面读取 Django readiness 接口，展示基础服务是否可用于接收请求。
      </p>

      {readiness.isError && (
        <div role="alert" className="mt-6 rounded-xl border border-red-400/30 bg-red-400/10 p-4 text-red-100">
          无法连接后端健康检查，请确认 Django、PostgreSQL 和 Redis 已启动。
        </div>
      )}

      <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatusCard label="Frontend" ok detail="React 应用已加载" />
        <StatusCard label="Django" ok={djangoOk} loading={readiness.isPending} />
        <StatusCard label="PostgreSQL" ok={databaseOk} loading={readiness.isPending} />
        <StatusCard label="Redis" ok={redisOk} loading={readiness.isPending} />
      </div>
    </section>
  );
}

