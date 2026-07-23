import { X } from "lucide-react";
import type { ReactNode } from "react";

interface DrawerProps {
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
}

export function Drawer({ title, description, onClose, children }: DrawerProps) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="presentation">
      <button
        type="button"
        aria-label="关闭抽屉"
        onClick={onClose}
        className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        className="relative h-full w-full overflow-y-auto bg-slate-900 px-6 pb-10 pt-[max(env(safe-area-inset-top),2rem)] shadow-2xl lg:max-w-xl lg:border-l lg:border-white/10 lg:p-6"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 id="drawer-title" className="text-3xl font-semibold text-white">
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
        <div className="mt-8">{children}</div>
      </aside>
    </div>
  );
}
