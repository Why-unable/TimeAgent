import {
  Bell,
  Brain,
  CalendarDays,
  ChevronRight,
  Clock3,
  Lightbulb,
  MessageSquare,
  MonitorCog,
  Newspaper,
  ShieldCheck,
  SlidersHorizontal,
  Smartphone,
  UserRound,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { Drawer } from "../components/overlay/drawer";
import { useCurrentUser } from "../features/accounts/hooks";

type Destination = {
  to: string;
  label: string;
  icon: LucideIcon;
  onboardingId?: string;
  match: (path: string) => boolean;
};

type MeItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  onboardingId?: string;
  staffOnly?: boolean;
};

type MeGroup = { label: string; items: MeItem[] };

const primaryItems: Destination[] = [
  { to: "/today", label: "今天", icon: Clock3, onboardingId: "nav-today", match: (path) => path.startsWith("/today") },
  { to: "/chat", label: "助理", icon: MessageSquare, onboardingId: "nav-chat", match: (path) => path.startsWith("/chat") },
  {
    to: "/schedule",
    label: "计划",
    icon: CalendarDays,
    onboardingId: "nav-schedule",
    match: (path) => path.startsWith("/schedule") || path.startsWith("/calendar") || path.startsWith("/tasks") || path.startsWith("/planning"),
  },
];

const meGroups: MeGroup[] = [
  {
    label: "时间服务",
    items: [
      { to: "/reminders", label: "提醒", icon: Bell },
      { to: "/insights", label: "洞察", icon: Lightbulb },
      { to: "/briefings", label: "简报", icon: Newspaper },
      { to: "/approvals", label: "审批", icon: ShieldCheck },
    ],
  },
  {
    label: "个性化",
    items: [
      { to: "/settings/time", label: "时间偏好", icon: SlidersHorizontal, onboardingId: "nav-time-settings" },
      { to: "/settings/time-memory", label: "时间行为记忆", icon: Brain },
    ],
  },
  {
    label: "设置",
    items: [
      { to: "/settings/notifications", label: "通知设置", icon: Bell },
      { to: "/settings/account", label: "账户与安全", icon: UserRound },
      { to: "/settings/app", label: "应用设置", icon: Smartphone },
      { to: "/system-status", label: "系统状态", icon: MonitorCog, staffOnly: true },
    ],
  },
];

function isMePath(pathname: string) {
  return meGroups.some((group) => group.items.some((item) => pathname.startsWith(item.to)));
}

export function MobileNavigation() {
  const [meOpen, setMeOpen] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const currentUser = useCurrentUser();
  const location = useLocation();
  const previousLocationKey = useRef(location.key);
  const meActive = isMePath(location.pathname);

  useEffect(() => {
    if (previousLocationKey.current === location.key) return;
    previousLocationKey.current = location.key;
    setMeOpen(false);
  }, [location.key]);

  useEffect(() => {
    const viewport = window.visualViewport;
    let isMounted = true;
    const isTextEntry = (target: EventTarget | null) => {
      if (target instanceof HTMLTextAreaElement) return true;
      if (target instanceof HTMLElement && target.isContentEditable) return true;
      return target instanceof HTMLInputElement
        && !["button", "checkbox", "color", "file", "image", "radio", "range", "reset", "submit"].includes(target.type);
    };
    const updateKeyboardState = () => {
      if (!isMounted) return;
      const coveredHeight = viewport
        ? window.innerHeight - viewport.height - viewport.offsetTop
        : 0;
      setKeyboardOpen(viewport ? coveredHeight > 160 : isTextEntry(document.activeElement));
    };
    const onFocusIn = () => window.setTimeout(updateKeyboardState, 0);
    const onFocusOut = () => window.setTimeout(updateKeyboardState, 100);
    viewport?.addEventListener("resize", updateKeyboardState);
    viewport?.addEventListener("scroll", updateKeyboardState);
    window.addEventListener("focusin", onFocusIn);
    window.addEventListener("focusout", onFocusOut);
    updateKeyboardState();
    return () => {
      isMounted = false;
      viewport?.removeEventListener("resize", updateKeyboardState);
      viewport?.removeEventListener("scroll", updateKeyboardState);
      window.removeEventListener("focusin", onFocusIn);
      window.removeEventListener("focusout", onFocusOut);
    };
  }, []);

  return (
    <>
      <nav
        aria-label="移动端主导航"
        aria-hidden={keyboardOpen}
        inert={keyboardOpen}
        className={`fixed inset-x-0 bottom-0 z-40 grid max-w-[100vw] grid-cols-4 border-t border-slate-200 bg-white/95 px-2 pb-[max(env(safe-area-inset-bottom),0.375rem)] pt-1 shadow-[0_-4px_18px_rgba(15,23,42,0.06)] backdrop-blur transition-transform duration-150 lg:hidden ${
          keyboardOpen ? "pointer-events-none translate-y-full" : "translate-y-0"
        }`}
      >
        {primaryItems.map(({ to, label, icon: Icon, match, onboardingId }) => {
          const isActive = match(location.pathname);
          return (
            <Link
              key={to}
              to={to}
              data-onboarding-id={onboardingId}
              aria-current={isActive ? "page" : undefined}
              className={`flex min-h-12 min-w-0 flex-col items-center justify-center gap-0.5 rounded-lg text-[11px] font-medium transition ${
                isActive ? "font-semibold text-teal-800" : "text-slate-600"
              }`}
            >
              <span className={`grid size-8 place-items-center rounded-full ${isActive ? "bg-teal-50" : ""}`}>
                <Icon size={21} strokeWidth={isActive ? 2.2 : 1.8} aria-hidden="true" />
              </span>
              <span className="truncate">{label}</span>
              {isActive && <span className="sr-only">当前页面</span>}
            </Link>
          );
        })}
        <button
          type="button"
          data-onboarding-id="nav-more"
          aria-current={meActive ? "page" : undefined}
          aria-expanded={meOpen}
          aria-haspopup="dialog"
          onClick={() => setMeOpen(true)}
          className={`flex min-h-12 min-w-0 flex-col items-center justify-center gap-0.5 rounded-lg text-[11px] font-medium transition ${
            meActive ? "font-semibold text-teal-800" : "text-slate-600"
          }`}
        >
          <span className={`grid size-8 place-items-center rounded-full ${meActive ? "bg-teal-50" : ""}`}>
            <UserRound size={21} strokeWidth={meActive ? 2.2 : 1.8} aria-hidden="true" />
          </span>
          我的
          {meActive && <span className="sr-only">当前页面</span>}
        </button>
      </nav>
      {meOpen && (
        <Drawer title="我的" description="个人时间与应用设置" onClose={() => setMeOpen(false)}>
          <nav aria-label="我的功能" className="space-y-5 pb-2">
            {meGroups.map((group) => {
              const items = group.items.filter((item) => !item.staffOnly || currentUser.data?.is_staff);
              if (!items.length) return null;
              return (
                <section key={group.label} aria-label={group.label}>
                  <h4 className="px-1 text-xs font-semibold tracking-wide text-slate-500">{group.label}</h4>
                  <div className="mt-2 divide-y divide-slate-200 border-y border-slate-200">
                    {items.map(({ to, label: itemLabel, icon: ItemIcon, onboardingId }) => (
                      <NavLink
                        key={to}
                        to={to}
                        data-onboarding-id={onboardingId}
                        end={to === "/system-status"}
                        onClick={() => setMeOpen(false)}
                        className={({ isActive }) =>
                          `flex min-h-12 items-center gap-3 px-2 text-sm font-medium transition ${
                            isActive ? "text-teal-800" : "text-slate-700 hover:text-teal-800"
                          }`
                        }
                      >
                        <ItemIcon size={19} className="shrink-0 text-teal-700" aria-hidden="true" />
                        <span className="min-w-0 flex-1">{itemLabel}</span>
                        <ChevronRight size={17} className="shrink-0 text-slate-400" aria-hidden="true" />
                      </NavLink>
                    ))}
                  </div>
                </section>
              );
            })}
          </nav>
        </Drawer>
      )}
    </>
  );
}
