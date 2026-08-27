import { keys, useT } from '@simple-module-py/i18n';
import { Check, Copy } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

const RESET_AFTER_MS = 2000;

/**
 * The install command the hero hands the visitor, with a copy button.
 *
 * Two things this fixes over the inline markup it replaces:
 *
 * - The button was decorative. It carried `aria-label="Copy command"` and no
 *   handler at all, so the one control on the page that promises an action
 *   did nothing — worse than absent, because the label asserts otherwise.
 * - The command was `truncate`d. At 375px that hid 107px of a 370px string
 *   behind an ellipsis with no way to reveal it: `truncate` is
 *   `overflow: hidden`, not a scroll container, and the text is not
 *   selectable past the clip. A visitor on a phone could neither read the
 *   command nor copy it. It now wraps instead, so the full command is always
 *   on screen.
 */
export function CopyCommand({ command }: { command: string }) {
  const { t } = useT();
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear on unmount so the reset can't fire into a gone component, and so a
  // rapid second click restarts the window rather than stacking timeouts.
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(command);
    } catch {
      // Clipboard access is refused on insecure origins and by permission
      // policy. Say nothing rather than throw — the command is on screen and
      // selectable, which is the fallback either way.
      return;
    }
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), RESET_AFTER_MS);
  }, [command]);

  return (
    <div className="mx-auto mt-7 flex max-w-xl items-start gap-3 rounded-xl border border-white/[0.06] bg-slate-900 px-4 py-3 text-left font-mono text-sm shadow-lg">
      <span aria-hidden="true" className="shrink-0 pt-px text-primary-300">
        $
      </span>
      <code className="min-w-0 flex-1 break-all text-slate-200">{command}</code>
      <button
        type="button"
        onClick={copy}
        aria-label={t(keys.host.landing.copy_command)}
        className="shrink-0 rounded p-0.5 text-slate-400 transition-colors hover:text-slate-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-primary-300" aria-hidden="true" />
        ) : (
          <Copy className="h-3.5 w-3.5" aria-hidden="true" />
        )}
      </button>
      {/* Announced, not shown: the icon swap is the visual signal, but a
          screen-reader user gets no feedback from a silent icon change. */}
      <span aria-live="polite" className="sr-only">
        {copied ? t(keys.host.landing.command_copied) : ''}
      </span>
    </div>
  );
}
