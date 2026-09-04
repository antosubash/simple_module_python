import { Head, Link, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { ArrowLeft, RefreshCcw } from 'lucide-react';
import { useState } from 'react';
import { DetailFacts } from './components/DetailFacts';
import { PayloadCards } from './components/PayloadCards';
import { RetryConfirmDialog } from './components/RetryConfirmDialog';
import { StatusPill } from './components/StatusPill';
import { TracebackCard } from './components/TracebackCard';
import { RETRYABLE_STATUSES, type TaskDetail, VIEW_BASE } from './constants';
import { retryExecution } from './retry';

interface Props {
  execution: TaskDetail;
  /** Configured retry ceiling — the denominator in "attempt 2 of 3". */
  max_retries: number;
}

function Detail() {
  const { execution, max_retries: maxRetries } = usePage<{ props: Props }>()
    .props as unknown as Props;
  const { t } = useT();
  const { can } = usePermissions();
  const retryable = RETRYABLE_STATUSES.has(execution.status) && can('background_tasks.manage');

  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  // The first run is attempt 1, so a row that has been retried once is on its
  // second — `retries` counts the retries, not the attempts.
  const attempt = execution.retries + 1;

  async function handleRetry() {
    setBusy(true);
    const created = await retryExecution(execution);
    setBusy(false);
    setConfirming(false);
    if (created) router.visit(`${VIEW_BASE}/${created.id}`);
  }

  return (
    <>
      <Head title={t(keys.background_tasks.detail.head_title)} />
      <PageShell
        title={execution.task_name}
        titleClassName="font-mono text-[22px]"
        mono
        back={VIEW_BASE}
        // Both are hidden on phones: the strip below restates them at a size
        // the 390px frame can read, and the shell's header showed the same
        // pill and the same attempt count immediately above it.
        badge={<StatusPill status={execution.status} className="max-lg:hidden text-xs" />}
        description={
          <span className="font-mono max-lg:hidden">
            {t(keys.background_tasks.detail.description, {
              id: execution.id,
              attempt,
              max: maxRetries,
            })}
          </span>
        }
        actions={
          <>
            {/* Hidden on phones: the shell's top bar already carries a back
                chevron, and the retry lives at the foot of the page where a
                thumb is. */}
            <Button variant="outline" size="sm" asChild className="max-lg:hidden">
              <Link href={VIEW_BASE}>
                <ArrowLeft aria-hidden="true" />
                {t(keys.background_tasks.detail.back_button)}
              </Link>
            </Button>
            {retryable && (
              <Button size="sm" className="max-lg:hidden" onClick={() => setConfirming(true)}>
                <RefreshCcw aria-hidden="true" />
                {t(keys.background_tasks.detail.retry_button)}
              </Button>
            )}
          </>
        }
      >
        {/* Phone-only restatement of the header: the shell's bar has room for
            the task name and nothing else, so the state and the attempt count
            lead the page instead. */}
        <div className="mb-3.5 flex items-center justify-between gap-3 lg:hidden">
          <StatusPill status={execution.status} className="px-3 py-1 text-xs" />
          <span className="text-[13px] text-muted-foreground">
            {t(keys.background_tasks.detail.attempt, { attempt, max: maxRetries })}
          </span>
        </div>

        {/* `order` puts the traceback straight after the facts on a phone —
            the payload cards are reference material, the traceback is why
            anyone opened this page. On desktop the deck's order returns. */}
        <div className="grid gap-3.5 lg:grid-cols-[320px_1fr]">
          <DetailFacts execution={execution} className="order-1 lg:order-1 lg:row-span-2" />
          <PayloadCards execution={execution} className="order-3 lg:order-2" />
          {/* `h-full` so a short payload card does not leave the traceback
              floating with 300px of empty card under it. */}
          <TracebackCard traceback={execution.traceback} className="order-2 h-full lg:order-3" />
        </div>

        {retryable && (
          <Button
            className="mt-4 min-h-[50px] w-full lg:hidden"
            onClick={() => setConfirming(true)}
          >
            <RefreshCcw aria-hidden="true" />
            {t(keys.background_tasks.detail.retry_button)}
          </Button>
        )}

        <RetryConfirmDialog
          target={confirming ? execution : null}
          onOpenChange={(open) => !open && setConfirming(false)}
          onConfirm={handleRetry}
          busy={busy}
        />
      </PageShell>
    </>
  );
}

Detail.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Detail;
