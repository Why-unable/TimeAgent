import {
  CalendarDays,
  Bell,
  CheckSquare,
  Clock3,
  MessageSquare,
  MonitorCog,
  Settings,
  UserRound,
  ShieldCheck,
  Newspaper,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { useCurrentUser } from "../features/accounts/hooks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import { MobileNavigation } from "./mobile-navigation";

const navigation = [
  { to: "/", label: "系统状态", icon: MonitorCog },
  { to: "/today", label: "今天", icon: Clock3 },
  { to: "/chat", label: "聊天", icon: MessageSquare },
  { to: "/briefings", label: "简报", icon: Newspaper },
  { to: "/calendar", label: "日历", icon: CalendarDays },
  { to: "/tasks", label: "任务", icon: CheckSquare },
  { to: "/reminders", label: "提醒", icon: Bell },
  { to: "/approvals", label: "审批", icon: ShieldCheck },
  { to: "/settings/time", label: "时间偏好", icon: Settings },
  { to: "/settings/account", label: "账户与安全", icon: UserRound },
  { to: "/settings/notifications", label: "通知设置", icon: Bell },
];

export function AppLayout() {
  const currentUser = useCurrentUser();
  const preference = useCurrentUserPreference();
  const timezone =
    preference.data?.timezone ?? import.meta.env.VITE_DEFAULT_TIMEZONE ?? "Asia/Shanghai";

  return (
    <div data-color-scheme="dark" className="min-h-screen bg-slate-950 text-slate-100">
      <aside data-testid="desktop-sidebar" className="fixed inset-y-0 left-0 hidden w-64 border-r border-white/10 bg-slate-900/80 p-6 backdrop-blur lg:block">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-[0.28em] text-cyan-300">Time Agent</p>
          <h1 className="mt-2 text-xl font-semibold">时间工作台</h1>
          <p className="mt-3 text-xs text-slate-500">当前时区：{timezone}</p>
        </div>
        <nav className="space-y-2" aria-label="主导航">
          {navigation
            .filter(({ to }) => currentUser.data?.is_staff || to !== "/")
            .map((item) => (item.to === "/" ? { ...item, to: "/system-status" } : item))
            .map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/system-status"}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${
                  isActive
                    ? "bg-cyan-400/15 text-cyan-200"
                    : "text-slate-300 hover:bg-white/5 hover:text-white"
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="min-h-screen px-[var(--mobile-page-gutter)] pb-[calc(var(--mobile-bottom-nav-height)+env(safe-area-inset-bottom)+1rem)] pt-[max(env(safe-area-inset-top),2rem)] lg:ml-64 lg:px-10 lg:pb-10 lg:pt-8">
        <Outlet />
      </main>
      <MobileNavigation />
    </div>
  );
}
