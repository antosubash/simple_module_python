import { Link, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { ArrowLeft, RefreshCw, ServerCrash, ServerOff } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { API_BASE, VIEW_BASE } from './constants';

interface WorkerInfo {
  hostname: string;
  online: boolean;
  queues: string[];
  active_task_count: number;
  pool_size: number | null;
  total_processed: number | null;
  software: string | null;
}

interface WorkerSnapshot {
  broker_reachable: boolean;
  polled_at: string;
  workers: WorkerInfo[];
  error: string | null;
}

interface Props {
  snapshot: WorkerSnapshot;
}

function formatPolledAt(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString();
}

function WorkerCard({ worker }: { worker: WorkerInfo }) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span
            role="img"
            className={`mt-1.5 size-2.5 rounded-full ${
              worker.online ? 'bg-green-500' : 'bg-muted-foreground'
            }`}
            aria-label={worker.online ? 'online' : 'offline'}
          />
          <div>
            <h3 className="font-medium">{worker.hostname}</h3>
            {worker.software && <p className="text-xs text-muted-foreground">{worker.software}</p>}
          </div>
        </div>
        <Badge variant={worker.online ? 'secondary' : 'outline'}>
          {worker.online ? 'Online' : 'Offline'}
        </Badge>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">Active</dt>
          <dd className="font-medium">{worker.active_task_count}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Pool</dt>
          <dd className="font-medium">{worker.pool_size ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Processed</dt>
          <dd className="font-medium">{worker.total_processed ?? '—'}</dd>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <dt className="text-muted-foreground">Queues</dt>
          <dd className="flex flex-wrap gap-1">
            {worker.queues.length === 0 ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              worker.queues.map((q) => (
                <Badge key={q} variant="outline" className="font-normal">
                  {q}
                </Badge>
              ))
            )}
          </dd>
        </div>
      </dl>
    </Card>
  );
}

function Workers() {
  const { snapshot: initial } = usePage<{ props: Props }>().props as unknown as Props;
  const [snapshot, setSnapshot] = useState<WorkerSnapshot>(initial);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/workers`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        setSnapshot((await res.json()) as WorkerSnapshot);
      } else {
        toast.error(`Failed to refresh workers (HTTP ${res.status})`);
      }
    } catch {
      toast.error('Failed to refresh workers');
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageShell title="Workers" description="Celery workers connected to the broker.">
      <div className="mb-4 flex items-center justify-between gap-3">
        <Button variant="outline" size="sm" asChild>
          <Link href={VIEW_BASE}>
            <ArrowLeft className="mr-2 size-4" />
            Back to executions
          </Link>
        </Button>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            Last updated {formatPolledAt(snapshot.polled_at)}
          </span>
          <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
            <RefreshCw className={`mr-2 size-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {!snapshot.broker_reachable ? (
        <Card className="p-6">
          <div className="flex items-start gap-3">
            <ServerCrash className="size-5 text-destructive" />
            <div>
              <h3 className="font-medium">Broker unreachable</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                {snapshot.error ?? 'No error message reported.'}
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                Check the <code>SM_BG_TASKS_BROKER_URL</code> setting and confirm the broker process
                is running.
              </p>
            </div>
          </div>
        </Card>
      ) : snapshot.workers.length === 0 ? (
        <Card className="p-6">
          <div className="flex items-start gap-3">
            <ServerOff className="size-5 text-muted-foreground" />
            <div>
              <h3 className="font-medium">No workers connected</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                The broker is reachable but no Celery workers are responding. Start one with{' '}
                <code>uv run python scripts/run_worker.py</code>.
              </p>
            </div>
          </div>
        </Card>
      ) : (
        <div className="grid gap-3">
          {snapshot.workers.map((w) => (
            <WorkerCard key={w.hostname} worker={w} />
          ))}
        </div>
      )}
    </PageShell>
  );
}

Workers.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Workers;
