import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { InlineBanner } from '@simple-module-py/ui/components/InlineBanner';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { ServerCrash, ServerOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import { API_BASE, VIEW_BASE, type WorkerSnapshot } from '../constants';
import { diagnoseWorkerHealth, type WorkerHealthState } from '../worker-health';

interface Props {
  /** Tasks queued or already running — the backlog whose fate is in question. */
  backlog: number;
}

/** The diagnosed states that actually render a banner — `healthy` renders nothing. */
type BannerState = Exclude<WorkerHealthState, 'healthy'>;

function diagnose(snapshot: WorkerSnapshot): BannerState | null {
  const state = diagnoseWorkerHealth({
    brokerReachable: snapshot.broker_reachable,
    onlineWorkerCount: snapshot.workers.filter((w) => w.online).length,
  });
  return state === 'healthy' ? null : state;
}

/**
 * Warns when a backlog has nobody to work it.
 *
 * A queue of twelve with a healthy worker and a queue of twelve with no worker
 * at all render identically — same rows, same counts — and only one of them is
 * fine. Answering that needs the broker, which costs a full inspect timeout
 * even when everything is healthy (the probes wait out the timeout rather than
 * returning early). So this is deliberately *not* part of the page render:
 * the list paints immediately and the warning arrives a moment later, and only
 * when there is a backlog whose fate is actually in question.
 *
 * Silent on failure — a page that can't reach its own API should not invent a
 * diagnosis about the broker.
 */
export function WorkerHealthBanner({ backlog }: Props) {
  const { t } = useT();
  const [state, setState] = useState<BannerState | null>(null);

  useEffect(() => {
    if (backlog <= 0) {
      setState(null);
      return;
    }
    const controller = new AbortController();
    fetch(`${API_BASE}/workers`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
      .then((res) => (res.ok ? (res.json() as Promise<WorkerSnapshot>) : null))
      .then((snapshot) => snapshot && setState(diagnose(snapshot)))
      .catch(() => {
        /* offline, aborted, or forbidden — say nothing rather than guess */
      });
    return () => controller.abort();
  }, [backlog]);

  if (!state) return null;

  const isBrokerUnreachable = state === 'broker_unreachable';

  return (
    <InlineBanner
      icon={isBrokerUnreachable ? ServerCrash : ServerOff}
      tone="warning"
      align="start"
      title={
        isBrokerUnreachable
          ? t(keys.background_tasks.worker_health.broker_unreachable_title)
          : t(keys.background_tasks.worker_health.no_workers_title, { count: backlog })
      }
      description={
        isBrokerUnreachable
          ? t(keys.background_tasks.worker_health.broker_unreachable_detail)
          : t(keys.background_tasks.worker_health.no_workers_detail)
      }
      action={
        <Button variant="outline" size="sm" asChild>
          <Link href={`${VIEW_BASE}/workers`}>
            {t(keys.background_tasks.worker_health.view_workers)}
          </Link>
        </Button>
      }
    />
  );
}
