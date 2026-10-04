import { X } from "lucide-react";
import { App } from "@capacitor/app";
import { createPortal } from "react-dom";
import { useEffect, useId, useRef, type ReactNode } from "react";

import { isNativePlatform } from "../../platform";

interface DrawerProps {
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
}

export function Drawer({ title, description, onClose, children }: DrawerProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  const titleId = useId();

  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    if (!dialog) return;

    const appRoot = document.getElementById("root");
    const previousInert = appRoot?.inert ?? false;
    const previousAriaHidden = appRoot?.getAttribute("aria-hidden") ?? null;
    if (appRoot) {
      appRoot.inert = true;
      appRoot.setAttribute("aria-hidden", "true");
    }

    dialog.focus();

    const focusableElements = () => Array.from(dialog.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])',
    )).filter((element) =>
      !element.hasAttribute("hidden")
      && element.getAttribute("aria-hidden") !== "true"
      && getComputedStyle(element).display !== "none"
      && getComputedStyle(element).visibility !== "hidden",
    );

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = focusableElements();
      const first = focusable[0];
      const last = focusable.at(-1);
      const active = document.activeElement;
      if (!first || !last) {
        event.preventDefault();
        dialog.focus();
      } else if (event.shiftKey && (active === first || active === dialog || !dialog.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (appRoot) {
        appRoot.inert = previousInert;
        if (previousAriaHidden === null) appRoot.removeAttribute("aria-hidden");
        else appRoot.setAttribute("aria-hidden", previousAriaHidden);
      }
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  useEffect(() => {
    if (!isNativePlatform()) return;
    let disposed = false;
    let listener: { remove: () => Promise<void> } | null = null;
    void App.addListener("backButton", () => closeRef.current()).then((registered) => {
      if (disposed) void registered.remove();
      else listener = registered;
    });
    return () => {
      disposed = true;
      if (listener) void listener.remove();
    };
  }, []);

  return createPortal((
    <div className="fixed inset-0 z-50 flex items-end justify-center lg:items-stretch lg:justify-end" role="presentation">
      <button
        type="button"
        aria-label="关闭抽屉"
        aria-hidden="true"
        tabIndex={-1}
        onClick={onClose}
        className="mobile-overlay-backdrop absolute inset-0"
      />
      <aside
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="relative mt-auto h-[min(92dvh,48rem)] w-full overscroll-contain overflow-y-auto rounded-t-[var(--mobile-sheet-radius)] bg-white px-5 pb-[max(env(safe-area-inset-bottom),1rem)] pt-[max(env(safe-area-inset-top),1.25rem)] shadow-2xl lg:ml-auto lg:mt-0 lg:h-full lg:max-h-none lg:max-w-xl lg:rounded-none lg:border-l lg:border-slate-200 lg:p-6"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 id={titleId} className="text-xl font-semibold text-slate-900 sm:text-2xl">
              {title}
            </h3>
            {description && <p className="mt-1 text-sm text-slate-600">{description}</p>}
          </div>
          <button
            type="button"
            aria-label="关闭"
            onClick={onClose}
            className="grid min-h-11 min-w-11 place-items-center rounded-xl text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          >
            <X size={24} />
          </button>
        </div>
        <div className="mt-4">{children}</div>
      </aside>
    </div>
  ), document.body);
}
