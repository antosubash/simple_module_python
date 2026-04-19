import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card } from '@simple-module/ui/components/ui/card';
import { usePermissions } from '@simple-module/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { ArrowLeft, RefreshCcw } from 'lucide-react';
import type { ReactNode } from 'react';
import { RetryConfirmDialog } from './components/RetryConfirmDialog';
import { RETRYABLE_STATUSES, STATUS_BADGE_VARIANT, type TaskStatus, VIEW_BASE } from './constants';
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

function statusLabel(status: TaskStatus): string {
  return status[0].toUpperCase() + status.slice(1);
}

function pretty(value: unknown): string {
  if (value === null || value === undefined) return '—';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatTs(ts: string | null): string {
  return ts ? new Date(ts).toLocaleString() : '—';
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
  const { can } = usePermissions();
  const retryable = RETRYABLE_STATUSES.has(execution.status) && can('background_tasks.manage');

  async function handleRetry() {
    const created = await retryExecution(execution);
    if (created) router.visit(`${VIEW_BASE}/${created.id}`);
  }

  return (
    <PageShell
      title={execution.task_name}
      description={`Task execution ${execution.id}`}
      actions={
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link href={VIEW_BASE}>
              <ArrowLeft />
              Back to tasks
            </Link>
          </Button>
          {retryable && (
            <RetryConfirmDialog
              trigger={
                <Button size="sm">
                  <RefreshCcw />
                  Retry task
                </Button>
              }
              onConfirm={handleRetry}
            />
          )}
        </div>
      }
    >
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="p-4 lg:col-span-1">
          <h3 className="font-semibold mb-3">Details</h3>
          <dl className="text-sm space-y-2">
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Status</dt>
              <dd>
                <Badge variant={STATUS_BADGE_VARIANT[execution.status]}>
                  {statusLabel(execution.status)}
                </Badge>
              </dd>
            </div>
            <Row label="Queue" value={execution.queue} />
            <Row label="Retries" value={String(execution.retries)} />
            <Row label="Worker" value={execution.worker || '—'} />
            <Row label="Celery id" value={execution.celery_task_id || '—'} mono />
            <Row label="Queued at" value={formatTs(execution.queued_at)} />
            <Row label="Started at" value={formatTs(execution.started_at)} />
            <Row label="Finished at" value={formatTs(execution.finished_at)} />
            <Row label="Heartbeat" value={formatTs(execution.heartbeat_at)} />
            <Row label="Exception" value={execution.exception_type || '—'} />
            {execution.retried_from_id && (
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Retried from</dt>
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
          <JsonCard title="Arguments">
            <JsonBlock value={execution.args} />
          </JsonCard>
          <JsonCard title="Keyword arguments">
            <JsonBlock value={execution.kwargs} />
          </JsonCard>
          {execution.result !== null && (
            <JsonCard title="Result">
              <JsonBlock value={execution.result} />
            </JsonCard>
          )}
          <JsonCard title="Traceback">
            {execution.traceback ? (
              <pre className="text-xs bg-muted rounded p-3 overflow-x-auto whitespace-pre-wrap">
                {execution.traceback}
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">No traceback recorded.</p>
            )}
          </JsonCard>
        </div>
      </div>
    </PageShell>
  );
}

Detail.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Detail;
