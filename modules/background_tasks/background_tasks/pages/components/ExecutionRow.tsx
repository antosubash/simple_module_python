import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { TableCell, TableRow } from '@simple-module-py/ui/components/ui/table';
import { RefreshCcw } from 'lucide-react';
import {
  formatTs,
  RETRYABLE_STATUSES,
  STATUS_BADGE_VARIANT,
  STATUS_LABEL_KEY,
  VIEW_BASE,
} from '../constants';
import type { Execution } from '../retry';
import { RetryConfirmDialog } from './RetryConfirmDialog';

function formatDuration(started: string | null, finished: string | null): string {
  if (!started) return '—';
  const end = finished ? new Date(finished) : new Date();
  const ms = end.getTime() - new Date(started).getTime();
  if (ms < 0) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`;
}

interface Props {
  execution: Execution;
  canRetry: boolean;
  onRetry: (execution: Execution) => void;
}

export function ExecutionRow({ execution, canRetry, onRetry }: Props) {
  const { t } = useT();
  const retryable = RETRYABLE_STATUSES.has(execution.status) && canRetry;
  return (
    <TableRow>
      <TableCell>
        <div className="flex flex-col">
          <Link href={`${VIEW_BASE}/${execution.id}`} className="font-medium hover:underline">
            {execution.task_name}
          </Link>
          {execution.exception_type && (
            <span className="text-xs text-destructive">{execution.exception_type}</span>
          )}
        </div>
      </TableCell>
      <TableCell>
        <Badge variant={STATUS_BADGE_VARIANT[execution.status]}>
          {t(STATUS_LABEL_KEY[execution.status])}
        </Badge>
      </TableCell>
      <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
        {execution.queue}
      </TableCell>
      <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
        {formatTs(execution.queued_at)}
      </TableCell>
      <TableCell className="hidden sm:table-cell text-sm tabular-nums">
        {formatDuration(execution.started_at, execution.finished_at)}
      </TableCell>
      <TableCell className="hidden xl:table-cell text-sm text-muted-foreground">
        {execution.worker || '—'}
      </TableCell>
      <TableCell className="text-right">
        {retryable ? (
          <RetryConfirmDialog
            trigger={
              <Button variant="ghost" size="icon-sm">
                <RefreshCcw />
              </Button>
            }
            taskName={execution.task_name}
            args={execution.args ?? []}
            kwargs={execution.kwargs ?? {}}
            onConfirm={() => onRetry(execution)}
          />
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        )}
      </TableCell>
    </TableRow>
  );
}
