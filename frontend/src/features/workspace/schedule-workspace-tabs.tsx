import { NavLink } from "react-router-dom";

const tabs = [
  { to: "/calendar", label: "日程" },
  { to: "/tasks", label: "任务" },
  { to: "/reminders", label: "提醒" },
];

/** Shared switcher for the three parts of the planning workspace. */
export function ScheduleWorkspaceTabs() {
  return (
    <nav
      aria-label="时间管理工作区"
      className="mt-5 grid w-full grid-cols-3 gap-1 rounded-2xl border border-white/10 bg-slate-900/80 p-1 lg:mt-0 lg:w-fit lg:min-w-[30rem] lg:rounded-2xl"
      style={{ minHeight: "var(--mobile-control-height)" }}
    >
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) =>
            `flex min-h-[3rem] items-center justify-center rounded-xl px-3 text-center text-base font-semibold transition lg:min-w-36 ${
              isActive
                ? "bg-cyan-300 text-slate-950"
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
