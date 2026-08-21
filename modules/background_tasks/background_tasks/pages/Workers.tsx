import { Head, Link, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { ageOf, isStale, relativeAge } from '@simple-module-py/ui/lib/relative-time';
import { ArrowLeft, RefreshCw, ServerCrash, ServerOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { API_BASE, formatTs, VIEW_BASE, type WorkerInfo, type WorkerSnapshot } from './constants';

interface Props {
  snapshot: WorkerSnapshot;
}

function WorkerCard({ worker }: { worker: WorkerInfo }) {
  const { t } = useT();
  const onlineLabel = worker.online
    ? t(keys.background_tasks.workers.online)
    : t(keys.background_tasks.workers.offline);
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span
            role="img"
            className={`mt-1.5 size-2.5 rounded-full ${
              worker.online ? 'bg-green-500' : 'bg-muted-foreground'
            }`}
            aria-label={onlineLabel}
          />
          <div>
            <h3 className="font-medium">{worker.hostname}</h3>
            {worker.software && <p className="text-xs text-muted-foreground">{worker.software}</p>}
          </div>
        </div>
        <Badge variant={worker.online ? 'secondary' : 'outline'}>{onlineLabel}</Badge>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">{t(keys.background_tasks.workers.active)}</dt>
          <dd className="font-medium">{worker.active_task_count}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t(keys.background_tasks.workers.pool)}</dt>
          <dd className="font-medium">{worker.pool_size ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t(keys.background_tasks.workers.processed)}</dt>
          <dd className="font-medium">{worker.total_processed ?? '—'}</dd>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <dt className="text-muted-foreground">{t(keys.background_tasks.workers.queues)}</dt>
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
  const { t } = useT();
  const [snapshot, setSnapshot] = useState<WorkerSnapshot>(initial);
  const [loading, setLoading] = useState(false);

  // This page is a point-in-time poll that only updates when asked. Left open
  // on a second monitor it keeps rendering a healthy fleet long after that
  // fleet died — the one failure it exists to catch. Ticking a clock beside the
  // reading is what makes the page admit it has gone cold; the poll itself
  // stays manual, so nobody's open tab quietly hammers the broker.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(id);
  }, []);
  const age = ageOf(snapshot.polled_at, now);
  const stale = isStale(age);
  const rel = relativeAge(age);
  const ageLabel = rel.count === undefined ? t(rel.key) : t(rel.key, { count: rel.count });

  async function refresh() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/workers`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        setSnapshot((await res.json()) as WorkerSnapshot);
        // Don't wait up to a tick for the age to catch up with the new reading.
        setNow(Date.now());
      } else {
        toast.error(t(keys.background_tasks.workers.refresh_failed_status, { status: res.status }));
      }
    } catch {
      toast.error(t(keys.background_tasks.workers.refresh_failed));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Head title={t(keys.background_tasks.workers.title)} />
      <PageShell
        title={t(keys.background_tasks.workers.title)}
        description={t(keys.background_tasks.workers.description)}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <Button variant="outline" size="sm" asChild>
            <Link href={VIEW_BASE}>
              <ArrowLeft className="mr-2 size-4" />
              {t(keys.background_tasks.workers.back_button)}
            </Link>
          </Button>
          <div className="flex items-center gap-3">
            <span
              className={`text-xs ${stale ? 'text-amber-600' : 'text-muted-foreground'}`}
              title={t(keys.background_tasks.workers.polled_at, {
                ts: formatTs(snapshot.polled_at),
              })}
            >
              {t(keys.background_tasks.workers.updated, { age: ageLabel })}
            </span>
            {stale && (
              <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-700">
                {t(keys.background_tasks.workers.stale)}
              </Badge>
            )}
            <Button
              variant={stale ? 'default' : 'outline'}
              size="sm"
              onClick={refresh}
              disabled={loading}
            >
              <RefreshCw className={`mr-2 size-4 ${loading ? 'animate-spin' : ''}`} />
              {t(keys.background_tasks.workers.refresh)}
            </Button>
          </div>
        </div>

        {!snapshot.broker_reachable ? (
          <Card className="p-6">
            <div className="flex items-start gap-3">
              <ServerCrash className="size-5 text-destructive" />
              <div>
                <h3 className="font-medium">
                  {t(keys.background_tasks.workers.broker_unreachable_title)}
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {snapshot.error ?? t(keys.background_tasks.workers.no_error_reported)}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {t(keys.background_tasks.workers.broker_hint_prefix)}{' '}
                  <code>SM_BG_TASKS_BROKER_URL</code>{' '}
                  {t(keys.background_tasks.workers.broker_hint_suffix)}
                </p>
              </div>
            </div>
          </Card>
        ) : snapshot.workers.length === 0 ? (
          <Card className="p-6">
            <div className="flex items-start gap-3">
              <ServerOff className="size-5 text-muted-foreground" />
              <div>
                <h3 className="font-medium">{t(keys.background_tasks.workers.no_workers_title)}</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t(keys.background_tasks.workers.no_workers_hint_prefix)}{' '}
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
    </>
  );
}

Workers.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Workers;
