import { Head, Link, router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { cn } from '@simple-module-py/ui/lib/utils';
import { ArrowLeft, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { OutboxTable } from './components/OutboxTable';
import { VIEW_BASE } from './constants';
import {
  discardOutboxMessage,
  OPEN_OUTBOX_STATUSES,
  OUTBOX_STATUS_LABEL_KEY,
  type OutboxMessage,
  retryOutboxMessage,
} from './outbox';

interface Props {
  messages: OutboxMessage[];
  /** Undelivered rows per status: pending, running, dead. */
  counts: Record<string, number>;
  pagination: { page: number; per_page: number; total: number };
  filters: { status: string };
}

const RELOAD_ONLY = ['messages', 'counts', 'pagination'];

function Outbox({ messages, counts, pagination, filters }: Props) {
  const { t } = useT();
  const { can } = usePermissions();
  const canManage = can('background_tasks.manage');
  const [pendingDiscard, setPendingDiscard] = useState<OutboxMessage | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  function visit(status: string, page: number) {
    const query: Record<string, string | number> = {};
    if (status) query.status = status;
    if (page > 1) query.page = page;
    router.get(`${VIEW_BASE}/outbox`, query, { preserveScroll: true, preserveState: true });
  }

  async function act(message: OutboxMessage, run: (id: string) => Promise<boolean>) {
    setBusyId(message.id);
    try {
      await run(message.id);
    } finally {
      // Whatever the outcome: a refused action means the row moved on.
      router.reload({ only: RELOAD_ONLY });
      setBusyId(null);
    }
  }

  const segments = [
    { value: '', label: t(keys.background_tasks.outbox.filter_all), count: null },
    ...OPEN_OUTBOX_STATUSES.map((s) => ({
      value: s as string,
      label: t(OUTBOX_STATUS_LABEL_KEY[s]),
      count: counts[s] ?? 0,
    })),
  ];

  return (
    <>
      <Head title={t(keys.background_tasks.outbox.title)} />
      <PageShell
        title={t(keys.background_tasks.outbox.title)}
        description={t(keys.background_tasks.outbox.description)}
        back={VIEW_BASE}
        actions={
          <Button variant="outline" asChild className="max-lg:min-h-11">
            <Link href={VIEW_BASE}>
              <ArrowLeft aria-hidden="true" />
              {t(keys.background_tasks.outbox.back_button)}
            </Link>
          </Button>
        }
      >
        <div className="mb-4 flex flex-wrap gap-2">
          {segments.map((seg) => (
            <Button
              key={seg.value || 'all'}
              variant="outline"
              size="sm"
              className={cn(filters.status === seg.value && 'bg-secondary')}
              aria-pressed={filters.status === seg.value}
              onClick={() => visit(seg.value, 1)}
            >
              {seg.label}
              {seg.count !== null && (
                <span className="tabular-nums text-muted-foreground">{seg.count}</span>
              )}
            </Button>
          ))}
        </div>
        <OutboxTable
          messages={messages}
          canManage={canManage}
          busyId={busyId}
          onRetry={(m) => void act(m, retryOutboxMessage)}
          onDiscard={setPendingDiscard}
          page={pagination.page}
          perPage={pagination.per_page}
          total={pagination.total}
          onPageChange={(page) => visit(filters.status, page)}
        />
      </PageShell>
      <ConfirmActionDialog
        open={pendingDiscard !== null}
        onOpenChange={(open) => !open && setPendingDiscard(null)}
        icon={Trash2}
        title={t(keys.background_tasks.outbox.discard)}
        description={t(keys.background_tasks.outbox.discard_confirm, {
          handler: pendingDiscard?.handler_name ?? '',
        })}
        confirmLabel={t(keys.background_tasks.outbox.discard)}
        cancelLabel={t(keys.background_tasks.retry_dialog.cancel)}
        busy={busyId !== null}
        onConfirm={() => {
          if (pendingDiscard) {
            void act(pendingDiscard, discardOutboxMessage).finally(() => setPendingDiscard(null));
          }
        }}
      />
    </>
  );
}

Outbox.layout = [AdminLayout];
export default Outbox;
