import { keys, useT } from '@simple-module-py/i18n';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { useEffect, useRef, useState } from 'react';

interface Props {
  traceback: string | null;
  className?: string;
}

/**
 * The stack trace, on a terminal.
 *
 * Dark because that is where a Python traceback is read everywhere else — the
 * shape is already familiar, and a light `<pre>` in a card reads as prose. The
 * final line is tinted because it is the only line most readers need: the
 * frames above it say where, that line says what.
 */
export function TracebackCard({ traceback, className }: Props) {
  const { t } = useT();
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  async function copy() {
    if (!traceback) return;
    try {
      await navigator.clipboard.writeText(traceback);
    } catch {
      // Clipboard is unavailable over plain http and in some webviews. The
      // text is still selectable, so degrade quietly rather than throw an
      // error at someone already reading one.
      return;
    }
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1500);
  }

  // The exception itself is the last line; everything above it is the path
  // that got there. Split rather than mapped so the transcript stays one text
  // node — a traceback has no items, only a shape.
  const trimmed = traceback?.replace(/\s+$/, '') ?? '';
  const lastBreak = trimmed.lastIndexOf('\n');
  const frames = lastBreak === -1 ? '' : trimmed.slice(0, lastBreak + 1);
  const exceptionLine = lastBreak === -1 ? trimmed : trimmed.slice(lastBreak + 1);

  return (
    <Card className={`gap-2.5 overflow-hidden p-4 lg:p-[18px] ${className ?? ''}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-bold font-display">
          {t(keys.background_tasks.detail.traceback)}
        </span>
        {traceback && (
          <button
            type="button"
            onClick={copy}
            className="rounded text-[12.5px] font-medium text-primary-700 hover:underline max-lg:min-h-11 max-lg:px-2"
          >
            {copied ? t(keys.background_tasks.detail.copied) : t(keys.background_tasks.detail.copy)}
          </button>
        )}
      </div>
      {traceback ? (
        <pre className="max-h-[28rem] overflow-auto rounded-[10px] bg-slate-900 px-4 py-4 font-mono text-[12.5px] leading-[1.8] text-slate-200">
          {frames}
          <span className="text-red-300">{exceptionLine}</span>
        </pre>
      ) : (
        <p className="text-sm text-muted-foreground">
          {t(keys.background_tasks.detail.no_traceback)}
        </p>
      )}
    </Card>
  );
}
