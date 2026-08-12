import { Check, ChevronRight, Compass, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import {
  hasCompletedOnboarding,
  markOnboardingCompleted,
  ONBOARDING_START_EVENT,
  resetOnboarding,
} from "../../features/onboarding/storage";

type TourStep = {
  id: string;
  title: string;
  description: string;
  anchorId?: string;
  actionLabel?: string;
};

type HighlightRect = {
  top: number;
  right: number;
  bottom: number;
  left: number;
  width: number;
  height: number;
};

const welcomeStep: TourStep = {
  id: "welcome",
  title: "欢迎使用 Time Agent",
  description: "用一分钟认识主要功能。接下来请点击被高亮的入口，一步步完成探索。",
};

const finishStep: TourStep = {
  id: "finish",
  title: "主要功能已经认识完了",
  description: "建议先完成时间、位置和内容偏好设置，再到聊天页告诉 Time Steward 你的安排。以后可在“应用设置”重新查看本引导。",
};

const sharedNavigationSteps: TourStep[] = [
  {
    id: "today",
    title: "从“今天”开始",
    description: "这里汇总今天的日程、任务和提醒，帮助你快速了解当天节奏。",
    anchorId: "nav-today",
    actionLabel: "打开“今天”",
  },
  {
    id: "chat",
    title: "直接告诉助理你的需求",
    description: "在聊天页用自然语言查询安排、创建日程、整理任务或设置提醒。高风险操作会先要求确认。",
    anchorId: "nav-chat",
    actionLabel: "打开“聊天”",
  },
  {
    id: "schedule",
    title: "集中管理日程",
    description: "这里可以查看日历，并进入任务和提醒管理；最终业务状态以后端数据为准。",
    anchorId: "nav-schedule",
    actionLabel: "打开“日程”",
  },
];

const desktopSettingsStep: TourStep = {
  id: "settings",
  title: "先完成个人偏好",
  description: "设置时区、当前位置、新闻主题和操作确认偏好后，简报与时间理解会更准确。",
  anchorId: "nav-time-settings",
  actionLabel: "打开“偏好设置”",
};

const mobileMoreStep: TourStep = {
  id: "more",
  title: "更多功能都在这里",
  description: "简报、审批、记忆、通知、账户和应用设置都可以从“更多”进入。",
  anchorId: "nav-more",
  actionLabel: "打开“更多”",
};

function isDesktopViewport(): boolean {
  return globalThis.matchMedia?.("(min-width: 1024px)").matches ?? false;
}

function findVisibleAnchor(anchorId: string): HTMLElement | null {
  const elements = document.querySelectorAll<HTMLElement>(`[data-onboarding-id="${anchorId}"]`);
  return Array.from(elements).find((element) => {
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }) ?? null;
}

function measureHighlight(element: HTMLElement): HighlightRect {
  const rect = element.getBoundingClientRect();
  const padding = 7;
  const left = Math.max(0, rect.left - padding);
  const top = Math.max(0, rect.top - padding);
  const right = Math.min(window.innerWidth, rect.right + padding);
  const bottom = Math.min(window.innerHeight, rect.bottom + padding);
  return {
    top,
    right,
    bottom,
    left,
    width: right - left,
    height: bottom - top,
  };
}

function Spotlight({ rect }: { rect: HighlightRect }) {
  const shade = "fixed z-[80] bg-slate-950/75 backdrop-blur-[1px]";
  return (
    <>
      <div className={shade} style={{ inset: `0 0 auto 0`, height: rect.top }} />
      <div className={shade} style={{ inset: `${rect.bottom}px 0 0 0` }} />
      <div className={shade} style={{ left: 0, top: rect.top, width: rect.left, height: rect.height }} />
      <div className={shade} style={{ left: rect.right, right: 0, top: rect.top, height: rect.height }} />
      <div
        className="pointer-events-none fixed z-[90] rounded-2xl border-2 border-cyan-300 shadow-[0_0_0_5px_rgba(103,232,249,0.18),0_0_32px_rgba(34,211,238,0.45)]"
        style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}
      />
    </>
  );
}

export function OnboardingTour({ userId }: { userId?: number }) {
  const location = useLocation();
  const [active, setActive] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [desktop, setDesktop] = useState(isDesktopViewport);
  const [highlight, setHighlight] = useState<HighlightRect | null>(null);
  const targetRef = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const steps = useMemo(
    () => [
      welcomeStep,
      ...sharedNavigationSteps,
      ...(desktop ? [desktopSettingsStep] : [mobileMoreStep, desktopSettingsStep]),
      finishStep,
    ],
    [desktop],
  );
  const step = steps[Math.min(stepIndex, steps.length - 1)];

  useEffect(() => {
    if (userId === undefined) return;
    setStepIndex(0);
    setActive(!hasCompletedOnboarding(userId));
  }, [userId]);

  useEffect(() => {
    const updateViewport = () => setDesktop(isDesktopViewport());
    window.addEventListener("resize", updateViewport);
    return () => window.removeEventListener("resize", updateViewport);
  }, []);

  useEffect(() => {
    if (userId === undefined) return;
    const restart = () => {
      resetOnboarding(userId);
      setStepIndex(0);
      setActive(true);
    };
    window.addEventListener(ONBOARDING_START_EVENT, restart);
    return () => window.removeEventListener(ONBOARDING_START_EVENT, restart);
  }, [userId]);

  useEffect(() => {
    if (!active) return;
    dialogRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && userId !== undefined) {
        markOnboardingCompleted(userId);
        setActive(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [active, stepIndex, userId]);

  useEffect(() => {
    if (!active || !step.anchorId) {
      targetRef.current = null;
      setHighlight(null);
      return;
    }
    let target: HTMLElement | null = null;
    const advance = () => setStepIndex((current) => Math.min(current + 1, steps.length - 1));
    const update = () => {
      const nextTarget = findVisibleAnchor(step.anchorId!);
      if (target !== nextTarget) {
        target?.removeEventListener("click", advance);
        target = nextTarget;
        target?.addEventListener("click", advance);
        targetRef.current = target;
      }
      setHighlight(target ? measureHighlight(target) : null);
    };
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      observer.disconnect();
      target?.removeEventListener("click", advance);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      targetRef.current = null;
    };
  }, [active, location.pathname, step.anchorId, steps.length]);

  if (!active || userId === undefined) return null;

  const dismiss = () => {
    markOnboardingCompleted(userId);
    setActive(false);
  };
  const isWelcome = step.id === "welcome";
  const isFinish = step.id === "finish";
  const progress = Math.max(0, stepIndex - 1);
  const navigableStepCount = steps.length - 2;

  return (
    <div aria-live="polite">
      {highlight ? <Spotlight rect={highlight} /> : <div className="fixed inset-0 z-[80] bg-slate-950/80 backdrop-blur-sm" />}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboarding-title"
        tabIndex={-1}
        className="fixed inset-x-4 bottom-[calc(var(--mobile-bottom-nav-height)+env(safe-area-inset-bottom)+1rem)] z-[100] mx-auto max-w-md rounded-3xl border border-cyan-200/70 bg-white p-5 text-slate-900 shadow-2xl outline-none lg:bottom-auto lg:left-[calc(50%+9rem)] lg:right-auto lg:top-1/2 lg:w-[26rem] lg:-translate-x-1/2 lg:-translate-y-1/2"
      >
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-cyan-100 text-teal-800">
            {isFinish ? <Check size={23} /> : <Compass size={23} />}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
              {isWelcome ? "首次使用引导" : isFinish ? "探索完成" : `${progress} / ${navigableStepCount}`}
            </p>
            <h2 id="onboarding-title" className="mt-1 text-xl font-semibold text-slate-950">{step.title}</h2>
          </div>
          <button type="button" onClick={dismiss} aria-label="关闭新手引导" className="rounded-xl p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900">
            <X size={19} />
          </button>
        </div>
        <p className="mt-4 text-sm leading-6 text-slate-700">{step.description}</p>
        {step.anchorId && !highlight && (
          <p role="status" className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900">正在定位对应入口…</p>
        )}
        <div className="mt-5 flex items-center justify-between gap-3">
          <button type="button" onClick={dismiss} className="rounded-xl px-3 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-900">
            暂时跳过
          </button>
          {isWelcome ? (
            <button type="button" onClick={() => setStepIndex(1)} className="inline-flex items-center gap-2 rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-800">
              开始探索 <ChevronRight size={17} />
            </button>
          ) : isFinish ? (
            <button type="button" onClick={dismiss} className="inline-flex items-center gap-2 rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-800">
              完成引导 <Check size={17} />
            </button>
          ) : (
            <button
              type="button"
              disabled={!highlight}
              onClick={() => targetRef.current?.click()}
              className="inline-flex items-center gap-2 rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-wait disabled:opacity-50"
            >
              {step.actionLabel} <ChevronRight size={17} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
