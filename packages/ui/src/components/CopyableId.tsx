import { Check, Copy } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

interface Props {
  /** The full value placed on the clipboard. */
  value: string;
  /** Shortened rendering, when the full value is too long to show. Defaults to `value`. */
  label?: string;
  /** Announced to screen readers and used as the button tooltip. */
  title?: string;
  className?: string;
}

/**
 * A monospace identifier chip with click-to-copy.
 *
 * Ids in this app (correlation ids, entity ids) are only useful if a human can
 * get them back out — into a support ticket, a log query, a bug report. Showing
 * one without a copy affordance means retyping a uuid by hand.
 */
export function CopyableId({ value, label, title, className = '' }: Props) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clearing on unmount stops the "copied" timer from firing into a dead
  // component when the user navigates away mid-flash.
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // Clipboard is unavailable over plain http and in some embedded
      // webviews. The id is still selectable as text, so degrade quietly
      // rather than throwing an error at someone already looking at one.
      return;
    }
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1500);
  }

  return (
    <button
      type="button"
      onClick={copy}
      title={title ?? value}
      aria-label={title ?? value}
      // 44px on phones: the chip is 20px tall by design and every caller puts
      // it in a dense table, where it is the only handle on a row's id.
      className={`inline-flex max-w-full items-center gap-1.5 rounded border border-border bg-muted/50 px-1.5 py-0.5 font-mono text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground max-sm:min-h-11 ${className}`}
    >
      <span className="truncate">{label ?? value}</span>
      {copied ? (
        <Check className="h-3 w-3 shrink-0 text-primary" aria-hidden="true" />
      ) : (
        <Copy className="h-3 w-3 shrink-0 opacity-60" aria-hidden="true" />
      )}
    </button>
  );
}
