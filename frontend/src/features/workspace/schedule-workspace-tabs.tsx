import { NavLink } from "react-router-dom";

const tabs = [
  { to: "/calendar", label: "日程" },
  { to: "/tasks", label: "任务" },
  { to: "/reminders", label: "提醒" },
];

/** Compact mobile switcher for the three parts of the planning workspace. */
export function ScheduleWorkspaceTabs() {
  return (
    <nav
      aria-label="时间管理工作区"
      className="mt-5 grid grid-cols-3 rounded-2xl border border-white/10 bg-slate-900/80 p-1 lg:hidden"
    >
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) =>
            `rounded-xl px-3 py-2.5 text-center text-sm font-semibold transition ${
              isActive
                ? "bg-cyan-300 text-slate-950"
                : "text-slate-400 active:bg-white/5 active:text-white"
            }`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
