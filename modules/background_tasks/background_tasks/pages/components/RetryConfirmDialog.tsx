import { keys, useT } from '@simple-module-py/i18n';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@simple-module-py/ui/components/ui/alert-dialog';
import type { ReactNode } from 'react';
import { useMemo } from 'react';

interface Props {
  trigger: ReactNode;
  onConfirm: () => void;
  taskName: string;
  args: unknown[];
  kwargs: Record<string, unknown>;
}

/** Pretty-print a payload, degrading to a marker rather than throwing on a cycle. */
function format(value: unknown): string {
  try {
    return JSON.stringify(value, null, 1)?.replace(/\n\s*/g, ' ') ?? String(value);
  } catch {
    return '<unserialisable>';
  }
}

export function RetryConfirmDialog({ trigger, onConfirm, taskName, args, kwargs }: Props) {
  const { t } = useT();
  const hasArgs = args.length > 0;
  const hasKwargs = Object.keys(kwargs).length > 0;
  // One dialog is mounted per retryable row (up to a full page of them), so
  // this is re-evaluated on every re-render of the row above it — memoize
  // rather than re-stringify a payload that hasn't changed.
  const formattedArgs = useMemo(() => (hasArgs ? format(args) : ''), [hasArgs, args]);
  const formattedKwargs = useMemo(() => (hasKwargs ? format(kwargs) : ''), [hasKwargs, kwargs]);

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {t(keys.background_tasks.retry_dialog.title, { name: taskName })}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {t(keys.background_tasks.retry_dialog.description)}
          </AlertDialogDescription>
        </AlertDialogHeader>

        {/* The arguments are the whole question: a retry re-sends this exact
            payload, so if it is what failed, retrying blind just fails again. */}
        {hasArgs || hasKwargs ? (
          <dl className="grid gap-1.5 rounded-md bg-muted/60 p-3 font-mono text-xs">
            {hasArgs && (
              <div className="flex gap-2">
                <dt className="shrink-0 text-muted-foreground">
                  {t(keys.background_tasks.retry_dialog.args_label)}
                </dt>
                <dd className="min-w-0 break-all">{formattedArgs}</dd>
              </div>
            )}
            {hasKwargs && (
              <div className="flex gap-2">
                <dt className="shrink-0 text-muted-foreground">
                  {t(keys.background_tasks.retry_dialog.kwargs_label)}
                </dt>
                <dd className="min-w-0 break-all">{formattedKwargs}</dd>
              </div>
            )}
          </dl>
        ) : (
          <p className="text-xs text-muted-foreground">
            {t(keys.background_tasks.retry_dialog.no_args)}
          </p>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel>{t(keys.background_tasks.retry_dialog.cancel)}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>
            {t(keys.background_tasks.retry_dialog.confirm)}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
