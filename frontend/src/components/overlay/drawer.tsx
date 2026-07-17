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
        className="relative h-full w-full max-w-xl overflow-y-auto border-l border-white/10 bg-slate-900 p-6 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 id="drawer-title" className="text-xl font-semibold text-white">
              {title}
            </h3>
            {description && <p className="mt-2 text-sm text-slate-400">{description}</p>}
          </div>
          <button
            type="button"
            aria-label="关闭"
            onClick={onClose}
            className="rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-white"
          >
            <X size={20} />
          </button>
        </div>
        <div className="mt-6">{children}</div>
      </aside>
    </div>
  );
}
