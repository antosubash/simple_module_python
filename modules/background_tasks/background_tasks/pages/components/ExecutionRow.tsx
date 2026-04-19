import { Link } from '@inertiajs/react';
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
} from '@simple-module/ui/components/ui/alert-dialog';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import { TableCell, TableRow } from '@simple-module/ui/components/ui/table';
import { RefreshCcw } from 'lucide-react';
import { RETRYABLE_STATUSES, STATUS_BADGE_VARIANT, type TaskStatus, VIEW_BASE } from '../constants';

export interface Execution {
  id: string;
  celery_task_id: string | null;
  task_name: string;
  status: TaskStatus;
  queue: string;
  retries: number;
  worker: string | null;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  exception_type: string | null;
  retried_from_id: string | null;
}

function statusLabel(status: TaskStatus): string {
  return status[0].toUpperCase() + status.slice(1);
}

function durationMs(started: string | null, finished: string | null): string {
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
          {statusLabel(execution.status)}
        </Badge>
      </TableCell>
      <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
        {execution.queue}
      </TableCell>
      <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
        {execution.queued_at ? new Date(execution.queued_at).toLocaleString() : '—'}
      </TableCell>
      <TableCell className="hidden sm:table-cell text-sm tabular-nums">
        {durationMs(execution.started_at, execution.finished_at)}
      </TableCell>
      <TableCell className="hidden xl:table-cell text-sm text-muted-foreground">
        {execution.worker || '—'}
      </TableCell>
      <TableCell className="text-right">
        {retryable ? (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="icon-sm">
                <RefreshCcw />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Retry this task?</AlertDialogTitle>
                <AlertDialogDescription>
                  A new task execution will be enqueued with the same arguments. The original row is
                  kept for history.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => onRetry(execution)}>Retry task</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        )}
      </TableCell>
    </TableRow>
  );
}

export { statusLabel };
