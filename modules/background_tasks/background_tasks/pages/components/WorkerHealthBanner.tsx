import { Link } from '@inertiajs/react';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { ServerCrash, ServerOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import { API_BASE, VIEW_BASE, type WorkerSnapshot } from '../constants';

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
  if (!snapshot.broker_reachable) {
    return {
      icon: ServerCrash,
      title: 'Broker unreachable',
      detail:
        'Nothing can be queued or run until the broker is back. The counts below are the last state written to the database.',
    };
  }
  if (snapshot.workers.every((w) => !w.online)) {
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
  const Icon = problem.icon;

  return (
    <Card className="mb-4 flex flex-row items-start justify-between gap-3 border-amber-300 bg-amber-50 px-4 py-3 dark:bg-amber-950/30">
      <div className="flex items-start gap-2.5">
        <Icon className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden="true" />
        <div>
          <p className="text-sm font-medium text-amber-900 dark:text-amber-200">{problem.title}</p>
          <p className="text-xs text-amber-800/80 dark:text-amber-200/70">{problem.detail}</p>
        </div>
      </div>
      <Button variant="outline" size="sm" asChild className="shrink-0">
        <Link href={`${VIEW_BASE}/workers`}>View workers</Link>
      </Button>
    </Card>
  );
}
