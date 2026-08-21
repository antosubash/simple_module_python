import { Head, Link, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { ArrowLeft, RefreshCcw } from 'lucide-react';
import type { ReactNode } from 'react';
import { RetryConfirmDialog } from './components/RetryConfirmDialog';
import {
  formatTs,
  RETRYABLE_STATUSES,
  STATUS_BADGE_VARIANT,
  STATUS_LABEL_KEY,
  type TaskStatus,
  VIEW_BASE,
} from './constants';
import { retryExecution } from './retry';

interface Execution {
  id: string;
  celery_task_id: string | null;
  task_name: string;
  status: TaskStatus;
  queue: string;
  args: unknown[];
  kwargs: Record<string, unknown>;
  result: Record<string, unknown> | null;
  traceback: string | null;
  exception_type: string | null;
  worker: string | null;
  retries: number;
  retried_from_id: string | null;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  heartbeat_at: string | null;
}

function pretty(value: unknown): string {
  if (value === null || value === undefined) return '—';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function JsonCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card className="p-4">
      <h3 className="font-semibold mb-2">{title}</h3>
      {children}
    </Card>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="text-xs bg-muted rounded p-3 overflow-x-auto whitespace-pre-wrap">
      {pretty(value)}
    </pre>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={mono ? 'font-mono text-xs break-all text-right' : 'text-right'}>{value}</dd>
    </div>
  );
}

function Detail() {
  const { execution } = usePage<{ props: { execution: Execution } }>().props as unknown as {
    execution: Execution;
  };
  const { t } = useT();
  const { can } = usePermissions();
  const retryable = RETRYABLE_STATUSES.has(execution.status) && can('background_tasks.manage');

  async function handleRetry() {
    const created = await retryExecution(execution);
    if (created) router.visit(`${VIEW_BASE}/${created.id}`);
  }

  return (
    <>
      <Head title={t(keys.background_tasks.detail.head_title)} />
      <PageShell
        title={execution.task_name}
        description={t(keys.background_tasks.detail.description, { id: execution.id })}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link href={VIEW_BASE}>
                <ArrowLeft />
                {t(keys.background_tasks.detail.back_button)}
              </Link>
            </Button>
            {retryable && (
              <RetryConfirmDialog
                trigger={
                  <Button size="sm">
                    <RefreshCcw />
                    {t(keys.background_tasks.detail.retry_button)}
                  </Button>
                }
                taskName={execution.task_name}
                args={execution.args ?? []}
                kwargs={execution.kwargs ?? {}}
                onConfirm={handleRetry}
              />
            )}
          </div>
        }
      >
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="p-4 lg:col-span-1">
            <h3 className="font-semibold mb-3">{t(keys.background_tasks.detail.meta)}</h3>
            <dl className="text-sm space-y-2">
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">{t(keys.background_tasks.detail.status)}</dt>
                <dd>
                  <Badge variant={STATUS_BADGE_VARIANT[execution.status]}>
                    {t(STATUS_LABEL_KEY[execution.status])}
                  </Badge>
                </dd>
              </div>
              <Row label={t(keys.background_tasks.detail.queue)} value={execution.queue} />
              <Row
                label={t(keys.background_tasks.detail.retries)}
                value={String(execution.retries)}
              />
              <Row label={t(keys.background_tasks.detail.worker)} value={execution.worker || '—'} />
              <Row
                label={t(keys.background_tasks.detail.celery_id)}
                value={execution.celery_task_id || '—'}
                mono
              />
              <Row
                label={t(keys.background_tasks.detail.queued_at)}
                value={formatTs(execution.queued_at)}
              />
              <Row
                label={t(keys.background_tasks.detail.started_at)}
                value={formatTs(execution.started_at)}
              />
              <Row
                label={t(keys.background_tasks.detail.finished_at)}
                value={formatTs(execution.finished_at)}
              />
              <Row
                label={t(keys.background_tasks.detail.heartbeat)}
                value={formatTs(execution.heartbeat_at)}
              />
              <Row
                label={t(keys.background_tasks.detail.exception)}
                value={execution.exception_type || '—'}
              />
              {execution.retried_from_id && (
                <div className="flex justify-between gap-3">
                  <dt className="text-muted-foreground">
                    {t(keys.background_tasks.detail.retried_from)}
                  </dt>
                  <dd>
                    <Link
                      href={`${VIEW_BASE}/${execution.retried_from_id}`}
                      className="hover:underline"
                    >
                      {execution.retried_from_id.slice(0, 8)}…
                    </Link>
                  </dd>
                </div>
              )}
            </dl>
          </Card>

          <div className="lg:col-span-2 flex flex-col gap-4">
            <JsonCard title={t(keys.background_tasks.detail.args)}>
              <JsonBlock value={execution.args} />
            </JsonCard>
            <JsonCard title={t(keys.background_tasks.detail.kwargs)}>
              <JsonBlock value={execution.kwargs} />
            </JsonCard>
            {execution.result !== null && (
              <JsonCard title={t(keys.background_tasks.detail.result)}>
                <JsonBlock value={execution.result} />
              </JsonCard>
            )}
            <JsonCard title={t(keys.background_tasks.detail.traceback)}>
              {execution.traceback ? (
                <pre className="text-xs bg-muted rounded p-3 overflow-x-auto whitespace-pre-wrap">
                  {execution.traceback}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {t(keys.background_tasks.detail.no_traceback)}
                </p>
              )}
            </JsonCard>
          </div>
        </div>
      </PageShell>
    </>
  );
}

Detail.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Detail;
