import { keys, useT } from '@simple-module-py/i18n';
import { PaginationBar } from '@simple-module-py/ui/components/PaginationBar';
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

/** Task, Status, Queue, Tenant, Queued, Duration, Actions. */
export const COLUMN_COUNT = 7;

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
            <TableHead className={`${TH} hidden md:table-cell`}>
              {t(keys.background_tasks.table.tenant)}
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
      <PaginationBar page={page} perPage={perPage} total={total} onPageChange={onPageChange} />
    </Card>
  );
}
