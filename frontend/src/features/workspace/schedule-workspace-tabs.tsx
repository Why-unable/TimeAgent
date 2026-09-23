import { NavLink } from "react-router-dom";

const tabs = [
  { to: "/calendar", label: "日程" },
  { to: "/tasks", label: "任务" },
  { to: "/planning", label: "规划" },
  { to: "/reminders", label: "提醒" },
];

/** Shared switcher for the three parts of the planning workspace. */
export function ScheduleWorkspaceTabs() {
  return (
    <nav
      aria-label="时间管理工作区"
      className="mt-3 grid w-full grid-cols-4 gap-1 rounded-xl border border-white/10 bg-slate-900/80 p-1 lg:mt-0 lg:w-fit lg:min-w-[36rem] lg:rounded-2xl"
      style={{ minHeight: "3.25rem" }}
    >
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) =>
            `flex min-h-11 items-center justify-center rounded-lg px-2 text-center text-sm font-semibold transition sm:text-base lg:min-w-32 ${
              isActive
                ? "bg-teal-600 text-slate-950"
                : "text-slate-300 active:bg-white/5 active:text-white"
            }`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
