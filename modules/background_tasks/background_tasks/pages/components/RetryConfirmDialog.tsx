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
  const hasArgs = args.length > 0;
  const hasKwargs = Object.keys(kwargs).length > 0;

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Retry {taskName}?</AlertDialogTitle>
          <AlertDialogDescription>
            Queues a new execution with the same arguments. The original row stays as it is, kept
            for history.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {/* The arguments are the whole question: a retry re-sends this exact
            payload, so if it is what failed, retrying blind just fails again. */}
        {hasArgs || hasKwargs ? (
          <dl className="grid gap-1.5 rounded-md bg-muted/60 p-3 font-mono text-xs">
            {hasArgs && (
              <div className="flex gap-2">
                <dt className="shrink-0 text-muted-foreground">args:</dt>
                <dd className="min-w-0 break-all">{format(args)}</dd>
              </div>
            )}
            {hasKwargs && (
              <div className="flex gap-2">
                <dt className="shrink-0 text-muted-foreground">kwargs:</dt>
                <dd className="min-w-0 break-all">{format(kwargs)}</dd>
              </div>
            )}
          </dl>
        ) : (
          <p className="text-xs text-muted-foreground">This task takes no arguments.</p>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Retry task</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
