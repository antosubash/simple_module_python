import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { EmptyState } from '@simple-module-py/ui/components/EmptyState';
import { TableEmptyRow } from '@simple-module-py/ui/components/TableEmptyRow';
import { Button } from '@simple-module-py/ui/components/ui/button';
import type { TFunction } from 'i18next';
import { Activity, type LucideIcon, PlugZap, ServerCog, ServerOff } from 'lucide-react';
import { VIEW_BASE } from '../constants';
import { diagnoseWorkerHealth } from '../worker-health';

export interface WorkerPresence {
  broker_reachable: boolean;
  worker_count: number;
}

interface TasksEmptyRowProps {
  /** A search term or status filter is narrowing the list. */
  filtered: boolean;
  columnCount: number;
  /** Fleet state, polled by the server only when the unfiltered list is empty. */
  presence: WorkerPresence | null;
  onClear: () => void;
}

interface EmptyCopy {
  icon: LucideIcon;
  title: string;
  description: string;
}

/**
 * Which "nothing here" message the executions table should show.
 *
 * "No task has run yet" is reassuring and wrong when the real cause is that no
 * worker was ever started: the queue is filling and nothing is draining it.
 * These are three different operator problems, so they get three different
 * messages. A filtered-empty list is handled by the caller — the fleet is not
 * why those rows are missing.
 */
function emptyCopy(t: TFunction, presence: WorkerPresence | null): EmptyCopy {
  const state = presence
    ? diagnoseWorkerHealth({
        brokerReachable: presence.broker_reachable,
        onlineWorkerCount: presence.worker_count,
      })
    : 'healthy';
  if (state === 'broker_unreachable') {
    return {
      icon: PlugZap,
      title: t(keys.background_tasks.tasks_empty.broker_unreachable_title),
      description: t(keys.background_tasks.tasks_empty.broker_unreachable_description),
    };
  }
  if (state === 'no_workers_online') {
    return {
      icon: ServerOff,
      title: t(keys.background_tasks.tasks_empty.no_workers_title),
      description: t(keys.background_tasks.tasks_empty.no_workers_description),
    };
  }
  return {
    icon: Activity,
    title: t(keys.background_tasks.tasks_empty.healthy_title),
    description: t(keys.background_tasks.tasks_empty.healthy_description),
  };
}

/** The executions table's empty row, in whichever of its four states applies. */
export function TasksEmptyRow({ filtered, columnCount, presence, onClear }: TasksEmptyRowProps) {
  const { t } = useT();
  const copy = emptyCopy(t, presence);
  return (
    <TableEmptyRow columnCount={columnCount}>
      {filtered ? (
        <EmptyState
          icon={Activity}
          title={t(keys.background_tasks.tasks_empty.filtered_title)}
          description={t(keys.background_tasks.tasks_empty.filtered_description)}
          action={
            <Button variant="outline" onClick={onClear}>
              {t(keys.background_tasks.tasks_empty.clear_filters)}
            </Button>
          }
        />
      ) : (
        <EmptyState
          icon={copy.icon}
          title={copy.title}
          description={copy.description}
          action={
            <Button variant="outline" asChild>
              <Link href={`${VIEW_BASE}/workers`}>
                <ServerCog className="mr-2 size-4" />
                {t(keys.background_tasks.worker_health.view_workers)}
              </Link>
            </Button>
          }
        />
      )}
    </TableEmptyRow>
  );
}
