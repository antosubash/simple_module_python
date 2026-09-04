import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import type { ReactNode } from 'react';
import type { Execution } from '../retry';
import { ExecutionRow } from './ExecutionRow';

/** Task, Status, Queue, Queued, Duration, Actions. */
export const COLUMN_COUNT = 6;

// Same header treatment as the other admin tables (users, audit log, flags).
const TH = 'text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground';

interface Props {
  executions: Execution[];
  canRetry: boolean;
  onRetry: (execution: Execution) => void;
  page: number;
  perPage: number;
  total: number;
  onPageChange: (page: number) => void;
  /** Rendered in place of the rows when there are none. */
  empty: ReactNode;
}

/**
 * The executions table and its footer.
 *
 * Paging lives *inside* the card because it describes this table and nothing
 * else, and it is always rendered — a footer that disappears below one page of
 * results makes the total disappear with it, and "how many are there" is a
 * question an operator asks before they ask anything else.
 */
export function ExecutionsTable({
  executions,
  canRetry,
  onRetry,
  page,
  perPage,
  total,
  onPageChange,
  empty,
}: Props) {
  const { t } = useT();
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  const from = total === 0 ? 0 : (page - 1) * perPage + 1;
  const to = Math.min(page * perPage, total);

  return (
    <Card className="overflow-hidden py-0">
      <Table>
        <TableHeader className="bg-secondary/40">
          <TableRow>
            <TableHead className={TH}>{t(keys.background_tasks.table.task)}</TableHead>
            <TableHead className={TH}>{t(keys.background_tasks.table.status)}</TableHead>
            <TableHead className={`${TH} hidden md:table-cell`}>
              {t(keys.background_tasks.table.queue)}
            </TableHead>
            <TableHead className={`${TH} hidden lg:table-cell`}>
              {t(keys.background_tasks.table.queued_at)}
            </TableHead>
            <TableHead className={`${TH} hidden sm:table-cell`}>
              {t(keys.background_tasks.table.duration)}
            </TableHead>
            <TableHead className={`${TH} text-right`}>
              {t(keys.background_tasks.table.actions)}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {executions.map((execution) => (
            <ExecutionRow
              key={execution.id}
              execution={execution}
              canRetry={canRetry}
              onRetry={onRetry}
            />
          ))}
          {executions.length === 0 && empty}
        </TableBody>
      </Table>
      <div className="flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground">
        <span>
          {t(keys.background_tasks.index.showing, {
            from,
            to,
            total: total.toLocaleString(),
          })}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="max-lg:min-h-11"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            {t(keys.background_tasks.index.previous)}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="max-lg:min-h-11"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
          >
            {t(keys.background_tasks.index.next)}
          </Button>
        </div>
      </div>
    </Card>
  );
}
