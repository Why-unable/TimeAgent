import {
  Bell,
  Brain,
  CalendarDays,
  Clock3,
  LayoutGrid,
  MessageSquare,
  MonitorCog,
  Newspaper,
  ShieldCheck,
  SlidersHorizontal,
  Smartphone,
  UserRound,
  Lightbulb,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { Drawer } from "../components/overlay/drawer";
import { useCurrentUser } from "../features/accounts/hooks";
import { isNativePlatform } from "../platform";

const primaryItems = [
  { to: "/today", label: "今天", icon: Clock3, onboardingId: "nav-today", match: (path: string) => path.startsWith("/today") },
  { to: "/chat", label: "聊天", icon: MessageSquare, onboardingId: "nav-chat", match: (path: string) => path.startsWith("/chat") },
  {
    to: "/calendar",
    label: "日程",
    icon: CalendarDays,
    onboardingId: "nav-schedule",
    match: (path: string) =>
      path.startsWith("/calendar")
      || path.startsWith("/tasks")
      || path.startsWith("/planning")
      || path.startsWith("/reminders"),
  },
];

const moreItems = [
  { to: "/insights", label: "洞察", description: "查看并处理时间风险", icon: Lightbulb },
  { to: "/briefings", label: "简报", description: "生成与查看每日简报", icon: Newspaper },
  { to: "/reminders", label: "提醒", description: "管理待发送提醒", icon: Bell },
  { to: "/approvals", label: "审批", description: "处理需要确认的操作", icon: ShieldCheck },
  { to: "/settings/time", label: "时间偏好", description: "时区、天气与新闻偏好", icon: SlidersHorizontal, onboardingId: "nav-time-settings" },
  { to: "/settings/time-memory", label: "时间行为记忆", description: "查看画像与管理记忆权限", icon: Brain },
  { to: "/settings/account", label: "账户与安全", description: "登录状态与账户操作", icon: UserRound },
  { to: "/settings/notifications", label: "通知设置", description: "邮件与 Web Push 通知", icon: Bell },
  { to: "/settings/app", label: "应用设置", description: "软件更新与使用引导", icon: Smartphone },
  { to: "/", label: "系统状态", description: "检查服务健康状态", icon: MonitorCog },
];

export function MobileNavigation() {
  const [moreOpen, setMoreOpen] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const currentUser = useCurrentUser();
  const location = useLocation();
  const pathname = location.pathname;
  const native = isNativePlatform();

  useEffect(() => {
    const viewport = window.visualViewport;
    const updateKeyboardState = () => {
      if (!viewport) return;
      const coveredHeight = window.innerHeight - viewport.height - viewport.offsetTop;
      setKeyboardOpen(coveredHeight > 160);
    };
    const onFocusIn = (event: FocusEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLTextAreaElement
        || (target instanceof HTMLInputElement && !["checkbox", "radio", "range"].includes(target.type))
      ) {
        setKeyboardOpen(true);
      }
    };
    const onFocusOut = () => window.setTimeout(updateKeyboardState, 100);
    viewport?.addEventListener("resize", updateKeyboardState);
    viewport?.addEventListener("scroll", updateKeyboardState);
    window.addEventListener("focusin", onFocusIn);
    window.addEventListener("focusout", onFocusOut);
    updateKeyboardState();
    return () => {
      viewport?.removeEventListener("resize", updateKeyboardState);
      viewport?.removeEventListener("scroll", updateKeyboardState);
      window.removeEventListener("focusin", onFocusIn);
      window.removeEventListener("focusout", onFocusOut);
    };
  }, []);

  const visibleMoreItems = moreItems
    .filter((item) => item.to !== "/reminders")
    .filter((item) => currentUser.data?.is_staff || item.to !== "/")
    .map((item) =>
      item.to === "/"
        ? { ...item, to: "/system-status", label: "系统状态", description: "检查服务健康状态" }
        : native && item.to === "/settings/notifications"
          ? { ...item, description: "邮件与应用提醒" }
        : item,
    );

  return (
    <>
      <nav
        aria-label="移动端主导航"
        className={`fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-white/10 bg-slate-900/95 px-2 pb-[max(env(safe-area-inset-bottom),0.625rem)] pt-2.5 shadow-[0_-12px_32px_rgba(2,6,23,0.45)] backdrop-blur transition-transform duration-150 lg:hidden ${
          keyboardOpen ? "pointer-events-none translate-y-full" : "translate-y-0"
        }`}
      >
        {primaryItems.map(({ to, label, icon: Icon, match, onboardingId }) => {
          const isActive = match(pathname);
          return (
            <Link
              key={to}
              to={to}
              data-onboarding-id={onboardingId}
              aria-current={isActive ? "page" : undefined}
              className={`flex min-h-[4.5rem] flex-col items-center justify-center gap-1.5 rounded-2xl text-sm font-medium transition ${
                isActive ? "bg-cyan-300/10 text-cyan-200" : "text-slate-400"
              }`}
            >
              <Icon size={25} strokeWidth={1.8} />
              {label}
            </Link>
          );
        })}
        <button
          type="button"
          data-onboarding-id="nav-more"
          onClick={() => setMoreOpen(true)}
          className="flex min-h-[4.5rem] flex-col items-center justify-center gap-1.5 rounded-2xl text-sm font-medium text-slate-400 transition hover:bg-white/5 hover:text-white"
        >
          <LayoutGrid size={25} strokeWidth={1.8} />
          更多
        </button>
      </nav>
      {moreOpen && (
        <Drawer title="更多功能" description="个人时间管理工具" onClose={() => setMoreOpen(false)}>
          <nav className="grid gap-2" aria-label="更多功能">
            {visibleMoreItems.map(({ to, label, description, icon: Icon, onboardingId }) => (
              <NavLink
                key={to}
                to={to}
                data-onboarding-id={onboardingId}
                end={to === "/system-status"}
                onClick={() => setMoreOpen(false)}
                className={({ isActive }) =>
                  `flex min-h-[4.75rem] items-center gap-4 rounded-2xl border p-5 transition ${
                    isActive
                      ? "border-cyan-300/30 bg-cyan-300/10 text-cyan-100"
                      : "border-white/10 bg-slate-950/40 text-slate-200 hover:border-white/20"
                  }`
                }
              >
                <Icon size={24} className="shrink-0 text-cyan-300" />
                <span className="min-w-0">
                  <span className="block text-base font-semibold">{label}</span>
                  <span className="mt-1 block text-sm text-slate-500">{description}</span>
                </span>
              </NavLink>
            ))}
          </nav>
        </Drawer>
      )}
    </>
  );
}
