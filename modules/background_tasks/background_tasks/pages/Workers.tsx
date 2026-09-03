import { Head, Link, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { ageOf, isStale } from '@simple-module-py/ui/lib/relative-time';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { WorkerCard } from './components/WorkerCard';
import { BrokerUnreachable, NoWorkers } from './components/WorkerEmptyStates';
import { API_BASE, formatClock, VIEW_BASE, type WorkerSnapshot } from './constants';

interface Props {
  snapshot: WorkerSnapshot;
  /** Broker url with the password stripped, for the unreachable state. */
  broker_url_redacted: string;
  /** Queues this install routes through, for the start-a-worker command. */
  queues: string[];
}

function Workers() {
  const {
    snapshot: initial,
    broker_url_redacted: brokerUrl,
    queues,
  } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const [snapshot, setSnapshot] = useState<WorkerSnapshot>(initial);
  const [loading, setLoading] = useState(false);

  // This page is a point-in-time poll that only updates when asked. Left open
  // on a second monitor it keeps rendering a healthy fleet long after that
  // fleet died — the one failure it exists to catch. The timestamp is
  // absolute, so a ticking clock is what lets the label admit it has gone
  // cold; the poll itself stays manual, so nobody's open tab quietly hammers
  // the broker.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(id);
  }, []);
  const stale = isStale(ageOf(snapshot.polled_at, now));

  async function refresh() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/workers`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        setSnapshot((await res.json()) as WorkerSnapshot);
        // Don't wait up to a tick for the staleness to catch up with the new
        // reading.
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
        back={VIEW_BASE}
        actions={
          <>
            <span className={`text-[13px] ${stale ? 'text-amber-700' : 'text-muted-foreground'}`}>
              {t(keys.background_tasks.workers.last_updated, {
                time: formatClock(snapshot.polled_at),
              })}
            </span>
            <Button
              variant="outline"
              onClick={refresh}
              disabled={loading}
              className="max-lg:min-h-11"
            >
              <RefreshCw className={loading ? 'animate-spin' : undefined} aria-hidden="true" />
              {t(keys.background_tasks.workers.refresh)}
            </Button>
            <Button variant="outline" asChild className="max-lg:min-h-11">
              <Link href={VIEW_BASE}>
                <ArrowLeft aria-hidden="true" />
                {t(keys.background_tasks.workers.back_button)}
              </Link>
            </Button>
          </>
        }
      >
        {!snapshot.broker_reachable ? (
          <BrokerUnreachable error={snapshot.error} brokerUrl={brokerUrl} />
        ) : snapshot.workers.length === 0 ? (
          <NoWorkers queues={queues ?? []} />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {snapshot.workers.map((worker) => (
              <WorkerCard key={worker.hostname} worker={worker} />
            ))}
          </div>
        )}
      </PageShell>
    </>
  );
}

Workers.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Workers;
