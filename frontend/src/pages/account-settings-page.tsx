import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { updateNickname } from "../api/auth";
import { queryClient } from "../app/query-client";
import { currentUserQueryKey, useCurrentUser, useLogout } from "../features/accounts/hooks";

export function AccountSettingsPage() {
  const navigate = useNavigate();
  const user = useCurrentUser();
  const logout = useLogout();
  const [nickname, setNickname] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (user.data) setNickname(user.data.display_name);
  }, [user.data]);

  async function saveNickname(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      const updated = await updateNickname(nickname);
      queryClient.setQueryData(currentUserQueryKey, updated);
      setMessage("昵称已保存。");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="mx-auto max-w-3xl">
      <p className="text-sm font-medium text-cyan-300">账户</p>
      <h2 className="mt-2 text-3xl font-semibold">账户与安全</h2>
      <div className="mt-8 rounded-2xl border border-white/10 bg-slate-900 p-6">
        <p className="text-sm text-slate-400">当前登录账号</p>
        <p className="mt-2 text-lg font-medium">
          {user.data?.is_guest ? "游客临时账号" : user.data?.email}
        </p>
        {user.data?.is_guest ? (
          <p className="mt-2 text-sm leading-6 text-amber-200">
            当前数据为临时数据，将在 {user.data.guest_expires_at ? new Date(user.data.guest_expires_at).toLocaleString("zh-CN") : "体验结束后"} 自动删除。退出后无法恢复该游客空间。
          </p>
        ) : (
          <p className="mt-2 text-sm text-slate-400">
            邮箱状态：{user.data?.is_email_verified ? "已验证" : "未验证"}
          </p>
        )}
        <form className="mt-6" onSubmit={saveNickname}>
          <label className="block text-sm text-slate-300">
            昵称
            <input
              required
              maxLength={150}
              value={nickname}
              onChange={(event) => setNickname(event.target.value)}
              className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none ring-cyan-300 focus:ring-2"
            />
          </label>
          <button type="submit" disabled={saving} className="mt-3 rounded-xl bg-cyan-300 px-4 py-2 text-sm font-medium text-slate-950 disabled:opacity-50">
            {saving ? "保存中…" : "保存昵称"}
          </button>
          {message && <p role="status" className="mt-2 text-sm text-emerald-200">{message}</p>}
        </form>
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
