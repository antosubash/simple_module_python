import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { RefreshCcw } from 'lucide-react';
import { useMemo } from 'react';

/** Everything the dialog needs about the row it is about to re-enqueue. */
export interface RetryTarget {
  task_name: string;
  args: unknown[];
  kwargs: Record<string, unknown>;
  retries: number;
}

interface Props {
  /** The row being retried, or `null` when the dialog is closed. */
  target: RetryTarget | null;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  busy?: boolean;
}

/** Pretty-print a payload, degrading to a marker rather than throwing on a cycle. */
function format(value: unknown): string {
  try {
    return JSON.stringify(value)?.replace(/,(?=\S)/g, ', ') ?? String(value);
  } catch {
    return '<unserialisable>';
  }
}

/**
 * "Are you sure?" for a single execution.
 *
 * The arguments are the whole question: a retry re-sends this exact payload,
 * so if the payload is what failed, retrying blind fails the same way. The
 * retry count is the second half — a task on its third attempt is telling you
 * something a first failure is not.
 */
export function RetryConfirmDialog({ target, onOpenChange, onConfirm, busy = false }: Props) {
  const { t } = useT();
  const args = target?.args ?? [];
  const kwargs = target?.kwargs ?? {};
  const hasArgs = args.length > 0;
  const hasKwargs = Object.keys(kwargs).length > 0;
  const formattedArgs = useMemo(() => (hasArgs ? format(args) : ''), [hasArgs, args]);
  const formattedKwargs = useMemo(() => (hasKwargs ? format(kwargs) : ''), [hasKwargs, kwargs]);
  const retries = target?.retries ?? 0;

  return (
    <ConfirmActionDialog
      open={target !== null}
      // Pinned while the request is in flight: closing under a busy confirm
      // would leave the operator unsure whether it went through.
      onOpenChange={(next) => {
        if (!busy) onOpenChange(next);
      }}
      tone="primary"
      icon={RefreshCcw}
      title={t(keys.background_tasks.retry_dialog.title, { name: target?.task_name ?? '' })}
      description={
        <>
          {t(keys.background_tasks.retry_dialog.description)}
          {/* Only when there is a history to report — "retried 0 times" is
              noise, and the deck's sentence assumes there was a previous go. */}
          {retries > 0 && (
            <> {t(keys.background_tasks.retry_dialog.retried_before, { count: retries })}</>
          )}
        </>
      }
      confirmLabel={t(keys.background_tasks.retry_dialog.confirm)}
      cancelLabel={t(keys.background_tasks.retry_dialog.cancel)}
      onConfirm={onConfirm}
      busy={busy}
    >
      {hasArgs || hasKwargs ? (
        <div className="rounded-lg border bg-secondary px-3 py-2.5 font-mono text-xs text-muted-foreground">
          <span className="break-all">
            {hasArgs && (
              <>
                {t(keys.background_tasks.retry_dialog.args_label)} {formattedArgs}
              </>
            )}
            {hasArgs && hasKwargs && <> · </>}
            {hasKwargs && (
              <>
                {t(keys.background_tasks.retry_dialog.kwargs_label)} {formattedKwargs}
              </>
            )}
          </span>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {t(keys.background_tasks.retry_dialog.no_args)}
        </p>
      )}
    </ConfirmActionDialog>
  );
}
