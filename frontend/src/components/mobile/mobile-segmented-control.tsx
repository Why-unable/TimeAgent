import { SegmentedControl } from "../ui/primitives";

/** Mobile segmented control: full width, compact selection. */
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
  return <SegmentedControl ariaLabel={ariaLabel} value={value} onChange={onChange} options={options} />;
}
