import { keys, useT } from '@simple-module-py/i18n';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Skeleton } from '@simple-module-py/ui/components/ui/skeleton';
import { cn } from '@simple-module-py/ui/lib/utils';
import type { ReactNode } from 'react';
import { EM_DASH, formatSoftware, formatUptime, type WorkerInfo } from '../constants';

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-bold font-display">{children}</div>
    </div>
  );
}

/**
 * One Celery worker.
 *
 * An offline card is dimmed rather than removed: a worker that stopped
 * answering is the most important thing on this page, and a fleet that
 * silently shrinks from four cards to three tells nobody anything. Pool and
 * Processed go to dashes because a worker that never answered `stats()`
 * reported no numbers; Active stays a real count, because "nothing is running
 * here" is the one thing a silent worker does tell you.
 */
export function WorkerCard({ worker }: { worker: WorkerInfo }) {
  const { t } = useT();
  const stateLabel = worker.online
    ? t(keys.background_tasks.workers.online)
    : t(keys.background_tasks.workers.offline);
  const software = formatSoftware(worker.software);
  const uptime = formatUptime(worker.uptime_seconds);
  // Deck shows "last heartbeat 6m ago" for an offline worker. Celery's inspect
  // cannot report anything about a worker that did not reply, and persisting
  // last-seen is a separate feature — so the card says what it knows.
  const state =
    worker.online && uptime ? t(keys.background_tasks.workers.uptime, { uptime }) : null;
  const offlineState = worker.online ? null : t(keys.background_tasks.workers.offline_state);
  const subline = [software, state ?? offlineState].filter(Boolean).join(' · ');

  return (
    <Card className={cn('gap-4 p-5', !worker.online && 'opacity-75')}>
      <div className="flex items-center gap-3">
        <span
          role="img"
          aria-label={stateLabel}
          className={cn(
            'size-2.5 shrink-0 rounded-full',
            worker.online ? 'bg-primary' : 'bg-muted-foreground',
          )}
        />
        <div className="min-w-0 flex-1">
          <code className="block truncate font-mono text-[15px] font-medium">
            {worker.hostname}
          </code>
          {subline && <div className="mt-0.5 text-xs text-muted-foreground">{subline}</div>}
        </div>
        <span
          className={cn(
            'shrink-0 rounded-full px-2.5 py-1 text-xs font-medium',
            worker.online
              ? 'bg-primary-600/10 text-primary-700'
              : 'bg-secondary text-muted-foreground',
          )}
        >
          {stateLabel}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label={t(keys.background_tasks.workers.active)}>
          {worker.active_task_count.toLocaleString()}
        </Stat>
        <Stat label={t(keys.background_tasks.workers.pool)}>
          {worker.pool_size?.toLocaleString() ?? EM_DASH}
        </Stat>
        <Stat label={t(keys.background_tasks.workers.processed)}>
          {worker.total_processed?.toLocaleString() ?? EM_DASH}
        </Stat>
        <div className="col-span-2 sm:col-span-1">
          <div className="text-xs text-muted-foreground">
            {t(keys.background_tasks.workers.queues)}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {worker.queues.length === 0 ? (
              <span className="text-sm text-muted-foreground">{EM_DASH}</span>
            ) : (
              worker.queues.map((queue) => (
                <code
                  key={queue}
                  className="rounded-full border px-2 py-0.5 font-mono text-[11.5px]"
                >
                  {queue}
                </code>
              ))
            )}
          </div>
        </div>
      </dl>
    </Card>
  );
}

/**
 * Stand-in for the fleet while the deferred broker poll is in flight.
 *
 * Two cards' worth of space in the same grid, so the routes table below does
 * not jump when the answer lands — whether that is cards, or an empty state.
 */
export function WorkersSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-busy="true" aria-label={label} className="grid gap-4 md:grid-cols-2">
      {[0, 1].map((i) => (
        <Card key={i} className="gap-4 p-5">
          <div className="flex items-center gap-3">
            <Skeleton className="size-2.5 rounded-full" />
            <Skeleton className="h-5 flex-1" />
            <Skeleton className="h-6 w-16 rounded-full" />
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[0, 1, 2, 3].map((j) => (
              <Skeleton key={j} className="h-11" />
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
