import { Link } from '@inertiajs/react';
import { InlineBanner } from '@simple-module-py/ui/components/InlineBanner';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { ServerCrash, ServerOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import { API_BASE, VIEW_BASE, type WorkerSnapshot } from '../constants';
import { diagnoseWorkerHealth } from '../worker-health';

interface Props {
  /** Tasks queued or already running — the backlog whose fate is in question. */
  backlog: number;
}

interface Problem {
  icon: typeof ServerOff;
  title: string;
  detail: string;
}

function diagnose(snapshot: WorkerSnapshot, backlog: number): Problem | null {
  const state = diagnoseWorkerHealth({
    brokerReachable: snapshot.broker_reachable,
    onlineWorkerCount: snapshot.workers.filter((w) => w.online).length,
  });
  if (state === 'broker_unreachable') {
    return {
      icon: ServerCrash,
      title: 'Broker unreachable',
      detail:
        'Nothing can be queued or run until the broker is back. The counts below are the last state written to the database.',
    };
  }
  if (state === 'no_workers_online') {
    return {
      icon: ServerOff,
      title: `${backlog} task${backlog === 1 ? '' : 's'} waiting, no worker running`,
      detail:
        'The broker is up but nothing is consuming the queue, so this backlog will not move on its own.',
    };
  }
  return null;
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
  const [problem, setProblem] = useState<Problem | null>(null);

  useEffect(() => {
    if (backlog <= 0) {
      setProblem(null);
      return;
    }
    const controller = new AbortController();
    fetch(`${API_BASE}/workers`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
      .then((res) => (res.ok ? (res.json() as Promise<WorkerSnapshot>) : null))
      .then((snapshot) => snapshot && setProblem(diagnose(snapshot, backlog)))
      .catch(() => {
        /* offline, aborted, or forbidden — say nothing rather than guess */
      });
    return () => controller.abort();
  }, [backlog]);

  if (!problem) return null;

  return (
    <InlineBanner
      icon={problem.icon}
      tone="warning"
      align="start"
      title={problem.title}
      description={problem.detail}
      action={
        <Button variant="outline" size="sm" asChild>
          <Link href={`${VIEW_BASE}/workers`}>View workers</Link>
        </Button>
      }
    />
  );
}
