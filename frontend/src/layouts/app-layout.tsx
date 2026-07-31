import {
  CalendarDays,
  Bell,
  Clock3,
  MessageSquare,
  MonitorCog,
  SlidersHorizontal,
  UserRound,
  ShieldCheck,
  Newspaper,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router-dom";

import { useCurrentUser } from "../features/accounts/hooks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import { MobileNavigation } from "./mobile-navigation";

type NavigationItem = {
  to: string;
  label: string;
  description: string;
  icon: LucideIcon;
  match?: (pathname: string) => boolean;
  staffOnly?: boolean;
};

const workspaceNavigation: NavigationItem[] = [
  { to: "/today", label: "今天", description: "今日节奏与待办", icon: Clock3 },
  { to: "/chat", label: "聊天", description: "智能时间助理", icon: MessageSquare },
  {
    to: "/calendar",
    label: "日程",
    description: "日程、任务与提醒",
    icon: CalendarDays,
    match: (pathname) =>
      pathname.startsWith("/calendar")
      || pathname.startsWith("/tasks")
      || pathname.startsWith("/reminders"),
  },
  { to: "/briefings", label: "简报", description: "每日信息汇总", icon: Newspaper },
  { to: "/approvals", label: "审批", description: "待确认操作", icon: ShieldCheck },
];

const settingsNavigation: NavigationItem[] = [
  {
    to: "/settings/time",
    label: "偏好设置",
    description: "时间、天气与内容",
    icon: SlidersHorizontal,
  },
  {
    to: "/settings/notifications",
    label: "通知设置",
    description: "提醒与投递渠道",
    icon: Bell,
  },
  {
    to: "/settings/account",
    label: "账户与安全",
    description: "个人资料与登录",
    icon: UserRound,
  },
  {
    to: "/system-status",
    label: "系统状态",
    description: "服务健康与诊断",
    icon: MonitorCog,
    staffOnly: true,
  },
];

export function AppLayout() {
  const currentUser = useCurrentUser();
  const preference = useCurrentUserPreference();
  const location = useLocation();
  const timezone =
    preference.data?.timezone ?? import.meta.env.VITE_DEFAULT_TIMEZONE ?? "Asia/Shanghai";
  const displayName = currentUser.data?.display_name || currentUser.data?.email || "Time Agent 用户";

  return (
    <div data-color-scheme="workspace" className="min-h-screen bg-slate-950 text-slate-100">
      <aside
        data-testid="desktop-sidebar"
        className="fixed inset-y-0 left-0 z-30 hidden w-72 flex-col border-r border-white/10 bg-slate-900/80 px-5 py-6 backdrop-blur lg:flex"
      >
        <Link to="/today" className="flex items-center gap-3 rounded-2xl px-3 py-2">
          <span className="grid size-11 place-items-center rounded-2xl bg-cyan-300 text-slate-950 shadow-sm">
            <Sparkles size={22} />
          </span>
          <span>
            <span className="block text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-300">
              Time Agent
            </span>
            <span className="mt-0.5 block text-lg font-semibold">时间工作台</span>
          </span>
        </Link>

        <DesktopNavigation
          label="工作区"
          items={workspaceNavigation}
          pathname={location.pathname}
          isStaff={Boolean(currentUser.data?.is_staff)}
        />
        <DesktopNavigation
          label="设置"
          items={settingsNavigation}
          pathname={location.pathname}
          isStaff={Boolean(currentUser.data?.is_staff)}
        />

        <div className="mt-auto rounded-2xl border border-white/10 bg-slate-950/50 p-4">
          <div className="flex items-center gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-full bg-cyan-300/15 text-cyan-300">
              <UserRound size={19} />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold text-slate-100">{displayName}</span>
              <span className="mt-0.5 block truncate text-xs text-slate-500">{timezone}</span>
            </span>
          </div>
        </div>
      </aside>
      <main className="min-h-screen px-[var(--mobile-page-gutter)] pb-[calc(var(--mobile-bottom-nav-height)+env(safe-area-inset-bottom)+1rem)] pt-[max(env(safe-area-inset-top),2rem)] lg:ml-72 lg:px-8 lg:pb-12 lg:pt-8 xl:px-12">
        <Outlet />
      </main>
      <MobileNavigation />
    </div>
  );
}

function DesktopNavigation({
  label,
  items,
  pathname,
  isStaff,
}: {
  label: string;
  items: NavigationItem[];
  pathname: string;
  isStaff: boolean;
}) {
  const visibleItems = items.filter((item) => isStaff || !item.staffOnly);
  return (
    <nav className="mt-8" aria-label={label}>
      <p className="px-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
        {label}
      </p>
      <div className="mt-2 space-y-1">
        {visibleItems.map(({ to, label: itemLabel, description, icon: Icon, match }) => {
          const active = match ? match(pathname) : pathname.startsWith(to);
          return (
            <Link
              key={to}
              to={to}
              aria-current={active ? "page" : undefined}
              className={`group flex items-center gap-3 rounded-2xl px-3 py-2.5 transition ${
                active
                  ? "bg-cyan-300/15 text-cyan-200"
                  : "text-slate-300 hover:bg-white/5 hover:text-white"
              }`}
            >
              <span
                className={`grid size-9 shrink-0 place-items-center rounded-xl transition ${
                  active ? "bg-cyan-300 text-slate-950" : "bg-white/5 text-slate-400"
                }`}
              >
                <Icon size={18} />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold">{itemLabel}</span>
                <span className="mt-0.5 block truncate text-[11px] text-slate-500">{description}</span>
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
