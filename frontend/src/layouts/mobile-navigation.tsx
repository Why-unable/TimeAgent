import { Bell, CalendarDays, CheckSquare, Clock3, MessageSquare } from "lucide-react";
import { NavLink } from "react-router-dom";

const items = [
  { to: "/today", label: "今天", icon: Clock3 },
  { to: "/chat", label: "聊天", icon: MessageSquare },
  { to: "/calendar", label: "日历", icon: CalendarDays },
  { to: "/tasks", label: "任务", icon: CheckSquare },
  { to: "/reminders", label: "提醒", icon: Bell },
];

export function MobileNavigation() {
  return (
    <nav
      aria-label="移动端导航"
      className="fixed inset-x-0 bottom-0 grid grid-cols-5 border-t border-white/10 bg-slate-900/95 px-2 py-2 backdrop-blur md:hidden"
    >
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex flex-col items-center gap-1 rounded-lg py-2 text-xs ${
              isActive ? "text-cyan-300" : "text-slate-400"
            }`
          }
        >
          <Icon size={18} />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
