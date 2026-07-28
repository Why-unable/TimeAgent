/** Mobile segmented control: full width, cyan-solid selection. */
export function MobileSegmentedControl<T extends string>({
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
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="grid w-full grid-cols-3 gap-1 rounded-xl bg-slate-950/70 p-1"
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(option.value)}
            className={`min-h-12 rounded-lg py-2 text-base font-medium transition ${
              selected ? "bg-cyan-300 text-slate-950" : "text-slate-300"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
