import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { RefreshCcw } from 'lucide-react';
import { QUEUE_ALL, SEGMENT_LABEL_KEY, STATUS_ALL } from '../constants';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  busy?: boolean;
  /** Active status filter, or '' for all. */
  status: string;
  /** Active queue filter, or '' for all. */
  queue: string;
}

/**
 * "Are you sure?" for the header's bulk retry.
 *
 * The action reaches rows the operator is not pointing at, so the dialog
 * restates the scope it will actually cover — the same two filters the
 * endpoint is given. A bulk action whose blast radius is implicit is one
 * people learn to fear rather than use.
 */
export function RetryAllDialog({
  open,
  onOpenChange,
  onConfirm,
  busy = false,
  status,
  queue,
}: Props) {
  const { t } = useT();
  const statusLabel =
    status && status !== STATUS_ALL && status in SEGMENT_LABEL_KEY
      ? t(SEGMENT_LABEL_KEY[status as keyof typeof SEGMENT_LABEL_KEY])
      : t(keys.background_tasks.retry_all_dialog.scope_all_statuses);
  const queueLabel =
    queue && queue !== QUEUE_ALL
      ? t(keys.background_tasks.retry_all_dialog.scope_queue, { queue })
      : t(keys.background_tasks.retry_all_dialog.scope_all_queues);

  return (
    <ConfirmActionDialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) onOpenChange(next);
      }}
      tone="primary"
      icon={RefreshCcw}
      title={t(keys.background_tasks.retry_all_dialog.title)}
      description={t(keys.background_tasks.retry_all_dialog.description)}
      confirmLabel={t(keys.background_tasks.retry_all_dialog.confirm)}
      cancelLabel={t(keys.background_tasks.retry_all_dialog.cancel)}
      onConfirm={onConfirm}
      busy={busy}
    >
      <div className="flex flex-wrap gap-2 rounded-lg border bg-secondary px-3 py-2.5 text-xs text-muted-foreground">
        <span>{statusLabel}</span>
        <span aria-hidden="true">·</span>
        <span>{queueLabel}</span>
      </div>
    </ConfirmActionDialog>
  );
}
