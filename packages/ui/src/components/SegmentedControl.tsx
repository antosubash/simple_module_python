import { cn } from '@simple-module-py/ui/lib/utils';

export interface SegmentedOption<V extends string> {
  value: V;
  label: string;
  /** Optional tally shown beside the label, e.g. how many rows that filter holds. */
  count?: number;
  disabled?: boolean;
}

interface SegmentedControlProps<V extends string> {
  value: V;
  onChange: (next: V) => void;
  options: SegmentedOption<V>[];
  'aria-label': string;
  size?: 'sm' | 'md';
  className?: string;
}

const SIZES = {
  sm: 'h-7 px-2.5 text-xs',
  md: 'h-8 px-3 text-sm',
} as const;

/**
 * One-of-N picker rendered as a raised chip inside a recessed track.
 *
 * It is a radio group, not a tab list: the options filter what a page shows
 * rather than swapping panels, and screen-reader users get "2 of 4 selected"
 * instead of being told to look for tab panels that do not exist.
 */
export function SegmentedControl<V extends string>({
  value,
  onChange,
  options,
  'aria-label': ariaLabel,
  size = 'md',
  className,
}: SegmentedControlProps<V>) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={cn('inline-flex items-center gap-1 rounded-lg bg-secondary p-1', className)}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          // biome-ignore lint/a11y/useSemanticElements: a native radio input cannot carry the raised-chip look this control is.
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={option.disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-md font-semibold transition-colors',
              // Phone hit target: 44px minimum, whatever the desktop size.
              'max-lg:min-h-11',
              'disabled:pointer-events-none disabled:opacity-50',
              SIZES[size],
              active
                ? 'bg-card text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {option.label}
            {option.count !== undefined && (
              <span
                className={cn(
                  'tabular-nums',
                  active ? 'text-muted-foreground' : 'text-muted-foreground/70',
                )}
              >
                {option.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
