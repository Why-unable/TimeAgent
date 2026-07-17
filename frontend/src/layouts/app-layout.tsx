import {
  CalendarDays,
  Bell,
  CheckSquare,
  Clock3,
  MessageSquare,
  MonitorCog,
  Settings,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { useCurrentUserPreference } from "../features/preferences/hooks";
import { MobileNavigation } from "./mobile-navigation";

const navigation = [
  { to: "/", label: "系统状态", icon: MonitorCog },
  { to: "/today", label: "今天", icon: Clock3 },
  { to: "/chat", label: "聊天", icon: MessageSquare },
  { to: "/calendar", label: "日历", icon: CalendarDays },
  { to: "/tasks", label: "任务", icon: CheckSquare },
  { to: "/reminders", label: "提醒", icon: Bell },
  { to: "/settings/time", label: "时间偏好", icon: Settings },
];

export function AppLayout() {
  const preference = useCurrentUserPreference();
  const timezone =
    preference.data?.timezone ?? import.meta.env.VITE_DEFAULT_TIMEZONE ?? "Asia/Shanghai";

  return (
    <div data-color-scheme="dark" className="min-h-screen bg-slate-950 text-slate-100">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-white/10 bg-slate-900/80 p-6 backdrop-blur md:block">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-[0.28em] text-cyan-300">Time Agent</p>
          <h1 className="mt-2 text-xl font-semibold">时间工作台</h1>
          <p className="mt-3 text-xs text-slate-500">当前时区：{timezone}</p>
        </div>
        <nav className="space-y-2" aria-label="主导航">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
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
      <main className="min-h-screen px-5 pb-24 pt-8 md:ml-64 md:px-10 md:pb-10">
        <Outlet />
      </main>
      <MobileNavigation />
    </div>
  );
}
