import type { ReactNode } from "react";

/** Section header used on mobile pages: icon, title, right-side count or action. */
export function MobileSectionHeader({
  icon,
  title,
  meta,
}: {
  icon?: ReactNode;
  title: string;
  meta?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
        {icon}
        {title}
      </h3>
      {meta && <span className="text-xs text-slate-500">{meta}</span>}
    </div>
  );
}
