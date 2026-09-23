import { forwardRef } from "react";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

const buttonVariants: Record<ButtonVariant, string> = {
  primary: "bg-teal-600 text-white shadow-sm hover:bg-teal-700",
  secondary: "border border-slate-200 bg-white text-slate-700 hover:border-teal-300 hover:text-teal-700",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
  danger: "bg-red-600 text-white shadow-sm hover:bg-red-700",
};

const buttonSizes: Record<ButtonSize, string> = {
  sm: "min-h-9 rounded-lg px-3 py-2 text-xs",
  md: "min-h-11 rounded-xl px-4 py-2.5 text-sm",
  lg: "min-h-12 rounded-xl px-5 py-3 text-base",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
}>(({ className = "", variant = "primary", size = "md", type = "button", ...props }, ref) => (
  <button
    ref={ref}
    type={type}
    className={`ui-button ui-button-${variant} inline-flex items-center justify-center gap-2 font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${buttonVariants[variant]} ${buttonSizes[size]} ${className}`}
    {...props}
  />
));
Button.displayName = "Button";

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-2xl border border-slate-200 bg-white shadow-[0_10px_30px_-24px_rgba(15,23,42,0.35)] ${className}`}
      {...props}
    />
  );
}

export function EmptyState({
  icon,
  title,
  description,
  actions,
  className = "",
}: {
  icon: ReactNode;
  title: string;
  description: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-2xl border border-dashed border-slate-300 px-5 py-10 text-center ${className}`}>
      {icon}
      <p className="mt-4 text-lg font-semibold text-slate-700">{title}</p>
      <p className="mt-2 text-sm text-slate-500">{description}</p>
      {actions && <div className="mt-5 flex justify-center gap-2">{actions}</div>}
    </div>
  );
}

export function PageHeader({
  icon,
  title,
  description,
  actions,
  className = "",
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={`flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between ${className}`}>
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-slate-900 lg:text-4xl">
          {icon}
          {title}
        </h2>
        {description && <p className="mt-2 text-sm leading-6 text-slate-500 lg:mt-3 lg:text-base">{description}</p>}
      </div>
      {actions && <div className="w-full shrink-0 lg:w-auto">{actions}</div>}
    </header>
  );
}

export function SegmentedControl<T extends string>({
  ariaLabel,
  value,
  onChange,
  options,
}: {
  ariaLabel: string;
  value: T;
  onChange: (next: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div role="tablist" aria-label={ariaLabel} className="grid w-full grid-cols-3 gap-1 rounded-xl bg-slate-950/70 p-1">
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(option.value)}
            className={`min-h-11 rounded-lg py-2 text-sm font-medium transition ${
              selected ? "bg-teal-600 text-slate-950" : "text-slate-300"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
