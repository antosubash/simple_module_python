import { keys, useT } from '@simple-module-py/i18n';
import { PaginationBar } from '@simple-module-py/ui/components/PaginationBar';
import { Card } from '@simple-module-py/ui/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { cn } from '@simple-module-py/ui/lib/utils';
import { EM_DASH, formatTs } from '../constants';
import { type LogItem, levelClass } from '../logs';

interface Props {
  logs: LogItem[];
  page: number;
  perPage: number;
  total: number;
  onPageChange: (page: number) => void;
  /** Show the task-id column (the search page); a task's own tab already knows it. */
  showTask?: boolean;
}

/** Log lines as a table with the shared pager underneath. */
export function LogTable({ logs, page, perPage, total, onPageChange, showTask = false }: Props) {
  const { t } = useT();
  return (
    <Card className="gap-0 overflow-hidden p-0" data-testid="log-table">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t(keys.background_tasks.logs.col_time)}</TableHead>
            <TableHead>{t(keys.background_tasks.logs.col_level)}</TableHead>
            <TableHead>{t(keys.background_tasks.logs.col_logger)}</TableHead>
            <TableHead>{t(keys.background_tasks.logs.col_message)}</TableHead>
            {showTask && <TableHead>{t(keys.background_tasks.logs.col_task)}</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {logs.length === 0 && (
            <TableRow>
              <TableCell colSpan={showTask ? 5 : 4} className="py-8 text-center">
                <p className="font-medium">{t(keys.background_tasks.logs.empty_title)}</p>
                <p className="mx-auto mt-1 max-w-prose text-sm text-muted-foreground">
                  {t(keys.background_tasks.logs.empty_description)}
                </p>
              </TableCell>
            </TableRow>
          )}
          {logs.map((row) => (
            <TableRow key={row.id}>
              <TableCell className="whitespace-nowrap font-mono text-xs">
                {formatTs(row.ts)}
              </TableCell>
              <TableCell className={cn('font-mono text-xs', levelClass(row.level))}>
                {row.level_name}
              </TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground">
                {row.logger}
              </TableCell>
              <TableCell className="max-w-[48ch] whitespace-pre-wrap break-words font-mono text-xs">
                {row.message}
              </TableCell>
              {showTask && (
                <TableCell className="font-mono text-xs">{row.task_id ?? EM_DASH}</TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <PaginationBar page={page} perPage={perPage} total={total} onPageChange={onPageChange} />
    </Card>
  );
}
