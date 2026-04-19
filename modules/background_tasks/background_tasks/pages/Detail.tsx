import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module/ui/components/PageShell';
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
import { Card } from '@simple-module/ui/components/ui/card';
import { usePermissions } from '@simple-module/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { fetchWithCsrf } from '@simple-module/ui/lib/csrf';
import { ArrowLeft, RefreshCcw } from 'lucide-react';
import { toast } from 'sonner';
import {
  API_BASE,
  RETRYABLE_STATUSES,
  STATUS_BADGE_VARIANT,
  type TaskStatus,
  VIEW_BASE,
} from './constants';

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

interface Props {
  execution: Execution;
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

function Detail() {
  const { execution } = usePage<{ props: Props }>().props as unknown as Props;
  const { can } = usePermissions();
  const canRetry = can('background_tasks.manage');
  const retryable = RETRYABLE_STATUSES.has(execution.status) && canRetry;

  async function handleRetry() {
    try {
      const res = await fetchWithCsrf(`${API_BASE}/executions/${execution.id}/retry`, {
        method: 'POST',
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const created = (await res.json()) as Execution;
      toast.success(`Task "${execution.task_name}" re-enqueued`);
      router.visit(`${VIEW_BASE}/${created.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to retry task');
    }
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
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button size="sm">
                  <RefreshCcw />
                  Retry task
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Retry this task?</AlertDialogTitle>
                  <AlertDialogDescription>
                    A new task execution will be enqueued with the same arguments.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleRetry}>Retry task</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
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
          <Card className="p-4">
            <h3 className="font-semibold mb-2">Arguments</h3>
            <pre className="text-xs bg-muted rounded p-3 overflow-x-auto whitespace-pre-wrap">
              {pretty(execution.args)}
            </pre>
          </Card>
          <Card className="p-4">
            <h3 className="font-semibold mb-2">Keyword arguments</h3>
            <pre className="text-xs bg-muted rounded p-3 overflow-x-auto whitespace-pre-wrap">
              {pretty(execution.kwargs)}
            </pre>
          </Card>
          {execution.result !== null && (
            <Card className="p-4">
              <h3 className="font-semibold mb-2">Result</h3>
              <pre className="text-xs bg-muted rounded p-3 overflow-x-auto whitespace-pre-wrap">
                {pretty(execution.result)}
              </pre>
            </Card>
          )}
          <Card className="p-4">
            <h3 className="font-semibold mb-2">Traceback</h3>
            {execution.traceback ? (
              <pre className="text-xs bg-muted rounded p-3 overflow-x-auto whitespace-pre-wrap">
                {execution.traceback}
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">No traceback recorded.</p>
            )}
          </Card>
        </div>
      </div>
    </PageShell>
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

Detail.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Detail;
