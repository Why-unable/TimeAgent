import { Navigate, Outlet } from "react-router-dom";

import { useCurrentUser } from "./hooks";

/** Keeps operational pages out of ordinary product routes. */
export function RequireStaff() {
  const user = useCurrentUser();

  if (user.isPending) return null;
  if (!user.data?.is_staff) return <Navigate to="/today" replace />;
  return <Outlet />;
}
