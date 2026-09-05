import { cn } from '@simple-module-py/ui/lib/utils';
import type React from 'react';
import { useRef } from 'react';

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

/** Which way each arrow key walks the group. Both axes, as APG asks for. */
const ARROW_STEPS: Record<string, 1 | -1> = {
  ArrowRight: 1,
  ArrowDown: 1,
  ArrowLeft: -1,
  ArrowUp: -1,
};

/**
 * First enabled option `step` hops away from `from`, wrapping round the ends.
 * Returns `from` when every other option is disabled.
 */
function seek<V extends string>(options: SegmentedOption<V>[], from: number, step: 1 | -1): number {
  const count = options.length;
  for (let hop = 1; hop <= count; hop += 1) {
    const index = (((from + step * hop) % count) + count) % count;
    if (!options[index]?.disabled) return index;
  }
  return from;
}

/**
 * One-of-N picker rendered as a raised chip inside a recessed track.
 *
 * It is a radio group, not a tab list: the options filter what a page shows
 * rather than swapping panels, and screen-reader users get "2 of 4 selected"
 * instead of being told to look for tab panels that do not exist.
 *
 * The role comes with keyboard behaviour attached, so it is implemented rather
 * than only announced: the group is a single tab stop (a roving `tabIndex`
 * parks it on the checked option), and Arrow/Home/End move the selection
 * inside it. Without that, Tab walked every option one by one and the arrow
 * keys did nothing — the opposite of what `radiogroup` promises a screen
 * reader.
 */
export function SegmentedControl<V extends string>({
  value,
  onChange,
  options,
  'aria-label': ariaLabel,
  size = 'md',
  className,
}: SegmentedControlProps<V>) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  const checkedIndex = options.findIndex((option) => option.value === value);
  // A group whose value matches no option — or matches a disabled one — must
  // still be reachable by Tab, so the first enabled option holds the stop.
  const tabStop =
    checkedIndex >= 0 && !options[checkedIndex]?.disabled
      ? checkedIndex
      : options.findIndex((option) => !option.disabled);

  /** Focus and select in one move: a radio group selects as it travels. */
  const moveTo = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    buttons.current[index]?.focus();
    if (option.value !== value) onChange(option.value);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = ARROW_STEPS[event.key];
    if (step) {
      event.preventDefault();
      moveTo(seek(options, index, step));
      return;
    }
    // Seeking forward from the last slot lands on the first enabled option,
    // and backward from the first lands on the last — the wrap does the work.
    if (event.key === 'Home') {
      event.preventDefault();
      moveTo(seek(options, options.length - 1, 1));
      return;
    }
    if (event.key === 'End') {
      event.preventDefault();
      moveTo(seek(options, 0, -1));
    }
  };

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={cn('inline-flex items-center gap-1 rounded-lg bg-secondary p-1', className)}
    >
      {options.map((option, index) => {
        const active = option.value === value;
        return (
          // biome-ignore lint/a11y/useSemanticElements: a native radio input cannot carry the raised-chip look this control is.
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={index === tabStop ? 0 : -1}
            ref={(node) => {
              buttons.current[index] = node;
            }}
            // Without this the accessible name is the label and the count run
            // together — "system28". The visible text stays as-is; only the
            // name a screen reader announces gets the separator.
            aria-label={option.count === undefined ? undefined : `${option.label} ${option.count}`}
            disabled={option.disabled}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => handleKeyDown(event, index)}
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
                aria-hidden
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
