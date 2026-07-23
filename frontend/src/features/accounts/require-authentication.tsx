import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useCurrentUser } from "./hooks";

export function RequireAuthentication() {
  const location = useLocation();
  const user = useCurrentUser();

  if (user.isPending) {
    return <div className="min-h-screen bg-slate-950 p-8 text-slate-300">正在验证登录状态…</div>;
  }
  if (user.isError) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
