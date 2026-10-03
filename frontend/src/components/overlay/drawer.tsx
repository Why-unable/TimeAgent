import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

interface DrawerProps {
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
}

export function Drawer({ title, description, onClose, children }: DrawerProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);

  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    if (!dialog) return;

    dialog.focus();

    const focusableElements = () => Array.from(dialog.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    )).filter((element) => !element.hasAttribute("hidden") && element.getAttribute("aria-hidden") !== "true");

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
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="presentation">
      <button
        type="button"
        aria-label="关闭抽屉"
        onClick={onClose}
        className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
      />
      <aside
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        tabIndex={-1}
        className="relative h-full w-full overflow-y-auto bg-slate-900 px-6 pb-10 pt-[max(env(safe-area-inset-top),2rem)] shadow-2xl lg:max-w-xl lg:border-l lg:border-white/10 lg:p-6"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 id="drawer-title" className="text-xl font-semibold text-white sm:text-2xl">
              {title}
            </h3>
            {description && <p className="mt-2 text-base text-slate-400">{description}</p>}
          </div>
          <button
            type="button"
            aria-label="关闭"
            onClick={onClose}
            className="rounded-2xl p-3 text-slate-400 hover:bg-white/5 hover:text-white"
          >
            <X size={24} />
          </button>
        </div>
        <div className="mt-5">{children}</div>
      </aside>
    </div>
  );
}
