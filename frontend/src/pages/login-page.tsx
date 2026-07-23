import { FormEvent, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import {
  confirmPasswordReset,
  loginAccount,
  registerAccount,
  requestPasswordReset,
} from "../api/auth";
import { ApiError } from "../api/client";
import { queryClient } from "../app/query-client";
import { currentUserQueryKey } from "../features/accounts/hooks";

type Mode = "login" | "register" | "reset";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "请求未完成，请稍后再试。";
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const resetUid = searchParams.get("reset_uid");
  const resetToken = searchParams.get("reset_token");
  const resetConfirmation = Boolean(resetUid && resetToken);
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const destination = (location.state as { from?: string } | null)?.from ?? "/today";
  const title = useMemo(() => {
    if (resetConfirmation) return "设置新密码";
    if (mode === "register") return "创建账号";
    if (mode === "reset") return "重置密码";
    return "登录 Time Agent";
  }, [mode, resetConfirmation]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    setStatus("");
    try {
      if (resetConfirmation && resetUid && resetToken) {
        await confirmPasswordReset(resetUid, resetToken, password);
        setStatus("密码已更新，请使用新密码登录。");
        navigate("/login", { replace: true });
        return;
      }
      if (mode === "reset") {
        await requestPasswordReset(email);
        setStatus("如该邮箱存在账号，重置链接已发送。请检查收件箱和垃圾邮件。 ");
        return;
      }
      const user = mode === "register"
        ? await registerAccount(email, password)
        : await loginAccount({ identifier: email, password });
      queryClient.setQueryData(currentUserQueryKey, user);
      navigate(destination, { replace: true });
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-5 py-12 text-slate-100">
      <section className="w-full max-w-md rounded-3xl border border-white/10 bg-slate-900 p-7 shadow-2xl shadow-black/30">
        <Link to="/" className="text-sm font-medium text-cyan-300">Time Agent</Link>
        <h1 className="mt-5 text-3xl font-semibold">{title}</h1>
        <p className="mt-2 text-sm text-slate-400">使用你的邮箱安全保存时间、日程与提醒。</p>

        {!resetConfirmation && (
          <div className="mt-6 flex rounded-xl bg-slate-950 p-1 text-sm" role="tablist">
            {(["login", "register", "reset"] as const).map((candidate) => (
              <button
                key={candidate}
                type="button"
                role="tab"
                aria-selected={mode === candidate}
                onClick={() => { setMode(candidate); setError(""); setStatus(""); }}
                className={`flex-1 rounded-lg px-2 py-2 transition ${mode === candidate ? "bg-cyan-300 font-medium text-slate-950" : "text-slate-400"}`}
              >
                {candidate === "login" ? "登录" : candidate === "register" ? "注册" : "忘记密码"}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={submit} className="mt-6 space-y-4">
          {!resetConfirmation && (
            <label className="block text-sm text-slate-300">
              邮箱
              <input
                autoComplete="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none ring-cyan-300 focus:ring-2"
                placeholder="you@example.com"
              />
            </label>
          )}
          {mode !== "reset" && (
            <label className="block text-sm text-slate-300">
              {resetConfirmation ? "新密码" : "密码"}
              <input
                autoComplete={resetConfirmation || mode === "register" ? "new-password" : "current-password"}
                type="password"
                minLength={8}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none ring-cyan-300 focus:ring-2"
                placeholder="至少 8 个字符"
              />
            </label>
          )}
          {error && <p role="alert" className="rounded-xl bg-red-400/10 p-3 text-sm text-red-200">{error}</p>}
          {status && <p role="status" className="rounded-xl bg-emerald-400/10 p-3 text-sm text-emerald-200">{status}</p>}
          <button type="submit" disabled={pending} className="w-full rounded-xl bg-cyan-300 px-5 py-3 font-medium text-slate-950 disabled:opacity-50">
            {pending ? "处理中…" : resetConfirmation ? "更新密码" : mode === "register" ? "创建账号" : mode === "reset" ? "发送重置链接" : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}
