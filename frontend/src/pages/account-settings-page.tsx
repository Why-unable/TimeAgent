import { useNavigate } from "react-router-dom";

import { useCurrentUser, useLogout } from "../features/accounts/hooks";

export function AccountSettingsPage() {
  const navigate = useNavigate();
  const user = useCurrentUser();
  const logout = useLogout();

  return (
    <section className="mx-auto max-w-3xl">
      <p className="text-sm font-medium text-cyan-300">账户</p>
      <h2 className="mt-2 text-3xl font-semibold">账户与安全</h2>
      <div className="mt-8 rounded-2xl border border-white/10 bg-slate-900 p-6">
        <p className="text-sm text-slate-400">当前登录账号</p>
        <p className="mt-2 text-lg font-medium">{user.data?.email}</p>
        <button
          type="button"
          disabled={logout.isPending}
          onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login", { replace: true }) })}
          className="mt-6 rounded-xl border border-red-300/40 px-5 py-3 text-sm font-medium text-red-200 disabled:opacity-50"
        >
          {logout.isPending ? "正在退出…" : "退出登录"}
        </button>
      </div>
    </section>
  );
}
