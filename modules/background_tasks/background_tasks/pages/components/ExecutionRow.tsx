import { Link, router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { TableCell, TableRow } from '@simple-module-py/ui/components/ui/table';
import { useRelativeTime } from '@simple-module-py/ui/hooks/use-relative-time';
import { formatDuration, RETRYABLE_STATUSES, VIEW_BASE } from '../constants';
import type { Execution } from '../retry';
import { StatusPill } from './StatusPill';

interface Props {
  execution: Execution;
  canRetry: boolean;
  onRetry: (execution: Execution) => void;
}

export function ExecutionRow({ execution, canRetry, onRetry }: Props) {
  const { t } = useT();
  const { ago } = useRelativeTime();
  const retryable = RETRYABLE_STATUSES.has(execution.status) && canRetry;
  const href = `${VIEW_BASE}/${execution.id}`;

  // The whole row navigates on click as a mouse convenience; the task name is
  // a real link, so keyboard and assistive-technology users reach the same
  // target without the row needing to impersonate a control.
  return (
    // `align-top`: the table is the card's flex child, so a short list let the
    // last row absorb the leftover height and its cells centred in it.
    <TableRow
      onClick={() => router.visit(href)}
      className="cursor-pointer align-top hover:bg-secondary/40"
    >
      <TableCell>
        <Link
          href={href}
          onClick={(e) => e.stopPropagation()}
          className="font-mono text-[13px] font-medium text-primary-700 hover:underline"
        >
          {execution.task_name}
        </Link>
      </TableCell>
      <TableCell>
        <StatusPill status={execution.status} />
      </TableCell>
      <TableCell className="hidden text-sm text-muted-foreground md:table-cell">
        {execution.queue}
      </TableCell>
      <TableCell className="hidden text-sm text-muted-foreground lg:table-cell">
        {ago(execution.queued_at)}
      </TableCell>
      <TableCell className="hidden text-sm tabular-nums text-muted-foreground sm:table-cell">
        {formatDuration(execution.started_at, execution.finished_at)}
      </TableCell>
      <TableCell className="text-right">
        {retryable ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onRetry(execution);
            }}
            className="rounded text-[12.5px] font-medium text-primary-700 hover:underline max-lg:min-h-11 max-lg:px-2"
          >
            {t(keys.background_tasks.table.retry)}
          </button>
        ) : null}
      </TableCell>
    </TableRow>
  );
}
