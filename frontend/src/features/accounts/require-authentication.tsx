import { Navigate, Outlet, useLocation } from "react-router-dom";

import { ApiError } from "../../api/client";
import { useCurrentUser } from "./hooks";

export function RequireAuthentication() {
  const location = useLocation();
  const user = useCurrentUser();

  if (user.isPending) {
    return <div className="min-h-screen bg-slate-950 p-8 text-slate-300">正在验证登录状态…</div>;
  }

  if (user.isError) {
    // 401/403 mean the user is genuinely signed out — DRF returns 401 when a
    // WWW-Authenticate-bearing authenticator is first, and 403 otherwise, so we
    // treat both as unauthenticated. Network drops, timeouts, and 5xx must not
    // eject the user to the login page — that would discard their session on a
    // temporary blip. Show a retry surface instead so a flaky mobile connection
    // can recover in place.
    const isUnauthenticated =
      user.error instanceof ApiError && (user.error.status === 401 || user.error.status === 403);
    if (isUnauthenticated) {
      return <Navigate to="/login" replace state={{ from: location.pathname }} />;
    }
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-950 px-6 text-center text-slate-300">
        <p className="text-base font-medium">暂时无法验证登录状态</p>
        <p className="max-w-sm text-sm text-slate-500">
          可能是网络连接不稳定或服务暂时不可用。请检查网络后重试。
        </p>
        <button
          type="button"
          onClick={() => user.refetch()}
          disabled={user.isFetching}
          className="rounded-xl bg-cyan-400/15 px-5 py-2.5 text-sm font-medium text-cyan-200 transition hover:bg-cyan-400/25 disabled:opacity-50"
        >
          {user.isFetching ? "正在重试…" : "重试"}
        </button>
      </div>
    );
  }

  return <Outlet />;
}
