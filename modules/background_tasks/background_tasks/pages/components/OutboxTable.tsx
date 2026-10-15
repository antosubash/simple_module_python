import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
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
import {
  OUTBOX_PILL_CLASS,
  OUTBOX_STATUS,
  OUTBOX_STATUS_LABEL_KEY,
  type OutboxMessage,
  shortName,
} from '../outbox';

const TH = 'text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground';
const COLUMN_COUNT = 7;

interface Props {
  messages: OutboxMessage[];
  canManage: boolean;
  busyId: string | null;
  onRetry: (message: OutboxMessage) => void;
  onDiscard: (message: OutboxMessage) => void;
  page: number;
  perPage: number;
  total: number;
  onPageChange: (page: number) => void;
}

/** First line of the stored error: the exception, not the traceback under it. */
function errorSummary(error: string | null): string {
  if (!error) return EM_DASH;
  return error.split('\n', 1)[0];
}

export function OutboxTable(props: Props) {
  const { messages, canManage, busyId, onRetry, onDiscard, page, perPage, total } = props;
  const { t } = useT();
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  const from = total === 0 ? 0 : (page - 1) * perPage + 1;
  const to = Math.min(page * perPage, total);

  return (
    <Card className="overflow-hidden py-0">
      <Table>
        <TableHeader className="bg-secondary/40">
          <TableRow>
            <TableHead className={TH}>{t(keys.background_tasks.outbox.col_event)}</TableHead>
            <TableHead className={TH}>{t(keys.background_tasks.outbox.col_status)}</TableHead>
            <TableHead className={`${TH} hidden md:table-cell`}>
              {t(keys.background_tasks.outbox.col_tenant)}
            </TableHead>
            <TableHead className={`${TH} hidden sm:table-cell`}>
              {t(keys.background_tasks.outbox.col_attempts)}
            </TableHead>
            <TableHead className={`${TH} hidden lg:table-cell`}>
              {t(keys.background_tasks.outbox.col_next_attempt)}
            </TableHead>
            <TableHead className={`${TH} hidden lg:table-cell`}>
              {t(keys.background_tasks.outbox.col_last_error)}
            </TableHead>
            <TableHead className={`${TH} text-right`}>
              {t(keys.background_tasks.outbox.col_actions)}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {messages.map((m) => (
            <TableRow key={m.id}>
              <TableCell>
                <div className="font-medium" title={m.event_key}>
                  {shortName(m.event_key)}
                </div>
                <div className="font-mono text-xs text-muted-foreground" title={m.handler_name}>
                  {m.handler_name}
                </div>
              </TableCell>
              <TableCell>
                <span
                  className={cn(
                    'inline-flex rounded-full px-2.5 py-0.5 text-[11.5px] font-medium',
                    OUTBOX_PILL_CLASS[m.status],
                  )}
                >
                  {t(OUTBOX_STATUS_LABEL_KEY[m.status])}
                </span>
              </TableCell>
              <TableCell className="hidden md:table-cell">
                {m.tenant_id ?? t(keys.background_tasks.outbox.platform)}
              </TableCell>
              <TableCell className="hidden sm:table-cell tabular-nums">{m.attempts}</TableCell>
              <TableCell className="hidden lg:table-cell">
                {m.status === OUTBOX_STATUS.PENDING ? formatTs(m.next_attempt_at) : EM_DASH}
              </TableCell>
              <TableCell
                className="hidden lg:table-cell max-w-[22rem] truncate text-xs"
                title={m.last_error ?? undefined}
              >
                {errorSummary(m.last_error)}
              </TableCell>
              <TableCell className="text-right">
                {canManage && (
                  <div className="flex justify-end gap-2">
                    {m.status === OUTBOX_STATUS.DEAD && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busyId === m.id}
                        onClick={() => onRetry(m)}
                      >
                        {t(keys.background_tasks.outbox.retry)}
                      </Button>
                    )}
                    {m.status !== OUTBOX_STATUS.RUNNING && (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busyId === m.id}
                        onClick={() => onDiscard(m)}
                      >
                        {t(keys.background_tasks.outbox.discard)}
                      </Button>
                    )}
                  </div>
                )}
              </TableCell>
            </TableRow>
          ))}
          {messages.length === 0 && (
            <TableRow>
              <TableCell colSpan={COLUMN_COUNT} className="py-12 text-center">
                <div className="font-medium">{t(keys.background_tasks.outbox.empty_title)}</div>
                <div className="text-sm text-muted-foreground">
                  {t(keys.background_tasks.outbox.empty_description)}
                </div>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <div className="flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground">
        <span>
          {t(keys.background_tasks.index.showing, { from, to, total: total.toLocaleString() })}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => props.onPageChange(page - 1)}
          >
            {t(keys.background_tasks.index.previous)}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => props.onPageChange(page + 1)}
          >
            {t(keys.background_tasks.index.next)}
          </Button>
        </div>
      </div>
    </Card>
  );
}
