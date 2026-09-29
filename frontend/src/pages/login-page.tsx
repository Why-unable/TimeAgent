import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import {
  type AuthOptions,
  confirmEmailVerification,
  confirmPasswordReset,
  getAuthOptions,
  registerAccount,
  requestEmailVerification,
  requestPasswordReset,
} from "../api/auth";
import { ApiError } from "../api/client";
import { queryClient } from "../app/query-client";
import { currentUserQueryKey } from "../features/accounts/hooks";
import { signIn, signInAsGuest } from "../features/accounts/session";

type Mode = "login" | "register" | "reset";
type LoginLocationState = { from?: string; notice?: string; email?: string };
const pendingVerificationEmailKey = "time-agent:pending-verification-email";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "请求未完成，请稍后再试。";
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const resetUid = searchParams.get("reset_uid");
  const resetToken = searchParams.get("reset_token");
  const verificationUid = searchParams.get("verify_uid");
  const verificationToken = searchParams.get("verify_token");
  const resetConfirmation = Boolean(resetUid && resetToken);
  const verificationConfirmation = Boolean(verificationUid && verificationToken);
  const locationState = location.state as LoginLocationState | null;
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState(() => locationState?.email ?? "");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [status, setStatus] = useState(() => locationState?.notice ?? "");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [verificationEmail, setVerificationEmail] = useState("");
  const [authOptions, setAuthOptions] = useState<AuthOptions | null>(null);
  const [authOptionsError, setAuthOptionsError] = useState(false);
  const [authOptionsNotice, setAuthOptionsNotice] = useState("");
  const [authOptionsRetry, setAuthOptionsRetry] = useState(0);
  const authTabRefs = useRef<Partial<Record<Mode, HTMLButtonElement>>>({});
  const authPanelRef = useRef<HTMLFormElement | null>(null);
  const registrationEnabled = authOptions?.registration_enabled ?? authOptionsError;
  const authModes: Mode[] = registrationEnabled
    ? ["login", "register", "reset"]
    : ["login", "reset"];
  const destination = locationState?.from ?? "/today";
  const title = useMemo(() => {
    if (verificationConfirmation) return "验证邮箱";
    if (resetConfirmation) return "设置新密码";
    if (mode === "register") return "创建账号";
    if (mode === "reset") return "重置密码";
    return "登录 Time Agent";
  }, [mode, resetConfirmation, verificationConfirmation]);

  useEffect(() => {
    let active = true;
    void getAuthOptions()
      .then((options) => {
        if (active) {
          setAuthOptions(options);
          setAuthOptionsError(false);
          setAuthOptionsNotice(authOptionsRetry > 0 ? "账号选项已重新读取。" : "");
        }
      })
      .catch(() => {
        if (active) {
          setAuthOptions(null);
          setAuthOptionsError(true);
          setAuthOptionsNotice("");
        }
      });
    return () => { active = false; };
  }, [authOptionsRetry]);

  useEffect(() => {
    if (authOptionsNotice) authPanelRef.current?.focus();
  }, [authOptionsNotice]);

  useEffect(() => {
    if (authOptions && !authOptions.registration_enabled && mode === "register") {
      setMode("login");
      setStatus("当前暂不开放注册。你可以使用已有账号登录。");
    }
  }, [authOptions, mode]);

  useEffect(() => {
    if (!verificationUid || !verificationToken) return;
    let active = true;
    setPending(true);
    setError("");
    void confirmEmailVerification(verificationUid, verificationToken)
      .then(() => {
        if (!active) return;
        const verifiedEmail = window.sessionStorage.getItem(pendingVerificationEmailKey) ?? "";
        window.sessionStorage.removeItem(pendingVerificationEmailKey);
        navigate("/login", {
          replace: true,
          state: {
            email: verifiedEmail,
            notice: "邮箱验证成功。请使用刚设置的密码登录。",
          },
        });
      })
      .catch((requestError: unknown) => {
        if (active) setError(errorMessage(requestError));
      })
      .finally(() => {
        if (active) setPending(false);
      });
    return () => { active = false; };
  }, [navigate, verificationToken, verificationUid]);

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
      let user;
      if (mode === "register") {
        await registerAccount(email, nickname, password);
        window.sessionStorage.setItem(pendingVerificationEmailKey, email);
        setVerificationEmail(email);
        setStatus("验证链接已发送至邮箱。请完成验证后再登录。");
        return;
      } else {
        user = await signIn({ identifier: email, password });
      }
      queryClient.setQueryData(currentUserQueryKey, user);
      navigate(destination, { replace: true });
    } catch (requestError) {
      if (
        mode === "register" &&
        requestError instanceof ApiError &&
        /account with this email already exists/i.test(requestError.message)
      ) {
        setMode("login");
        setVerificationEmail("");
        setStatus("该邮箱已经注册并可直接登录。请输入密码后登录。");
        return;
      }
      setError(errorMessage(requestError));
    } finally {
      setPending(false);
    }
  }

  async function enterGuestExperience() {
    setPending(true);
    setError("");
    setStatus("");
    try {
      const user = await signInAsGuest();
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

        {!resetConfirmation && !verificationConfirmation && (
          <div className="mt-6 flex rounded-xl bg-slate-950 p-1 text-sm" role="tablist" aria-label="账号访问方式">
            {authModes.map((candidate) => (
              <button
                key={candidate}
                ref={(element) => {
                  if (element) authTabRefs.current[candidate] = element;
                  else delete authTabRefs.current[candidate];
                }}
                type="button"
                role="tab"
                id={`auth-tab-${candidate}`}
                aria-controls="auth-panel"
                aria-selected={mode === candidate}
                tabIndex={mode === candidate ? 0 : -1}
                onClick={() => { setMode(candidate); setError(""); setStatus(""); }}
                onKeyDown={(event) => {
                  const index = authModes.indexOf(candidate);
                  const targetIndex = event.key === "ArrowRight"
                    ? (index + 1) % authModes.length
                    : event.key === "ArrowLeft"
                      ? (index + authModes.length - 1) % authModes.length
                      : event.key === "Home"
                        ? 0
                        : event.key === "End"
                          ? authModes.length - 1
                          : null;
                  if (targetIndex === null) return;
                  event.preventDefault();
                  const nextMode = authModes[targetIndex];
                  setMode(nextMode);
                  authTabRefs.current[nextMode]?.focus();
                }}
                className={`flex-1 rounded-lg px-2 py-2 transition ${mode === candidate ? "bg-cyan-300 font-medium text-slate-950" : "text-slate-400"}`}
              >
                {candidate === "login" ? "登录" : candidate === "register" ? "注册" : "忘记密码"}
              </button>
            ))}
          </div>
        )}
        {authOptions === null && !authOptionsError && !resetConfirmation && !verificationConfirmation && (
          <p className="mt-3 text-xs text-slate-400" role="status" aria-live="polite">正在读取可用的注册方式…</p>
        )}
        {authOptionsError && !resetConfirmation && !verificationConfirmation && (
          <div className="mt-3 flex items-center justify-between gap-3 rounded-xl bg-amber-300/10 p-3 text-xs text-amber-100" role="status">
            <span>暂时无法确认注册状态；游客体验已隐藏。你仍可登录或尝试注册。</span>
            <button type="button" onClick={() => setAuthOptionsRetry((value) => value + 1)} className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-md px-2 underline underline-offset-2">重试</button>
          </div>
        )}
        {authOptionsNotice && !resetConfirmation && !verificationConfirmation && (
          <p className="mt-3 text-xs text-emerald-200" role="status">{authOptionsNotice}</p>
        )}

        <form
          ref={authPanelRef}
          id="auth-panel"
          role={!resetConfirmation && !verificationConfirmation ? "tabpanel" : undefined}
          aria-labelledby={!resetConfirmation && !verificationConfirmation ? `auth-tab-${mode}` : undefined}
          tabIndex={-1}
          onSubmit={submit}
          className="mt-6 space-y-4"
        >
          {!resetConfirmation && !verificationConfirmation && (
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
          {mode === "register" && (
            <label className="block text-sm text-slate-300">
              昵称
              <input
                autoComplete="nickname"
                required
                value={nickname}
                onChange={(event) => setNickname(event.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none ring-cyan-300 focus:ring-2"
                placeholder="例如：小林"
              />
            </label>
          )}
          {mode !== "reset" && !verificationConfirmation && (
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
          {!verificationConfirmation && <button type="submit" disabled={pending} className="w-full rounded-xl bg-cyan-300 px-5 py-3 font-medium text-slate-950 disabled:opacity-50">
            {pending ? "处理中…" : resetConfirmation ? "更新密码" : mode === "register" ? "创建账号" : mode === "reset" ? "发送重置链接" : "登录"}
          </button>}
          {verificationEmail && !verificationConfirmation && (
            <button
              type="button"
              disabled={pending}
              onClick={() => void requestEmailVerification(verificationEmail).then(
                () => setStatus("验证链接已重新发送，请检查收件箱和垃圾邮件。"),
                (requestError: unknown) => setError(errorMessage(requestError)),
              )}
              className="w-full rounded-xl border border-cyan-300/50 px-5 py-3 font-medium text-cyan-200 disabled:opacity-50"
            >
              重新发送验证邮件
            </button>
          )}
        </form>
        {!resetConfirmation && !verificationConfirmation && mode !== "reset" && authOptions?.guest_access_enabled && (
          <div className="mt-6 border-t border-white/10 pt-6">
            <button
              type="button"
              disabled={pending}
              onClick={() => void enterGuestExperience()}
              className="w-full rounded-xl border border-cyan-300/50 bg-cyan-300/5 px-5 py-3 font-medium text-cyan-200 transition hover:bg-cyan-300/10 disabled:opacity-50"
            >
              {pending ? "正在进入…" : "游客体验（无需注册）"}
            </button>
            <p className="mt-3 text-xs leading-5 text-slate-400">
              将创建独立的临时空间，预置少量示例数据；数据默认保留 24 小时，且不启用邮件通知与长期记忆。
            </p>
          </div>
        )}
      </section>
    </main>
  );
}
