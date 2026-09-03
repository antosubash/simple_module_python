import { Head, Link, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { RefreshCcw, ServerCog } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { COLUMN_COUNT, ExecutionsTable } from './components/ExecutionsTable';
import { RetryAllDialog } from './components/RetryAllDialog';
import { RetryConfirmDialog } from './components/RetryConfirmDialog';
import { type StatusCounts, StatusStrip } from './components/StatusStrip';
import { TaskFilters } from './components/TaskFilters';
import { TasksEmptyRow, type WorkerPresence } from './components/TasksEmpty';
import { WorkerHealthBanner } from './components/WorkerHealthBanner';
import { QUEUE_ALL, STATUS_ALL, TASK_STATUS, VIEW_BASE } from './constants';
import { type Execution, retryAllFailed, retryExecution } from './retry';

interface Pagination {
  page: number;
  per_page: number;
  total: number;
}

interface Filters {
  status: string;
  task_name: string;
  queue: string;
}

interface Props {
  executions: Execution[];
  pagination: Pagination;
  filters: Filters;
  status_counts: StatusCounts;
  /** Every queue that has run work, for the dropdown. */
  queues: string[];
  /** Null unless the unfiltered list came back empty — see the index view. */
  worker_presence: WorkerPresence | null;
}

// A retry moves a row out of "failed", so the strip and the queue list are
// reloaded alongside the table — leaving them out leaves the tiles lying.
const RELOAD_ONLY = ['executions', 'pagination', 'status_counts', 'queues'];

function pushFilters(filters: Filters, page: number): void {
  const params: Record<string, string> = {};
  if (filters.task_name) params.q = filters.task_name;
  if (filters.status && filters.status !== STATUS_ALL) params.status = filters.status;
  if (filters.queue && filters.queue !== QUEUE_ALL) params.queue = filters.queue;
  if (page > 1) params.page = String(page);
  router.get(VIEW_BASE, params, { preserveState: true, preserveScroll: true });
}

function Index() {
  const {
    executions,
    pagination,
    filters: initialFilters,
    status_counts: statusCounts,
    queues,
    worker_presence: workerPresence,
  } = usePage<{ props: Props }>().props as unknown as Props;

  const { t } = useT();
  const { can } = usePermissions();
  const canRetry = can('background_tasks.manage');

  const [search, setSearch] = useState(initialFilters.task_name ?? '');
  const [retryTarget, setRetryTarget] = useState<Execution | null>(null);
  const [retryAllOpen, setRetryAllOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const statusValue = initialFilters.status || STATUS_ALL;
  const queueValue = initialFilters.queue || QUEUE_ALL;
  // Derived from the server-confirmed filters, not the live `search` input:
  // `workerPresence` reflects the last committed request, so mixing it with
  // unsubmitted local state would flash the wrong empty-state copy during the
  // debounce window between a keystroke and the resulting navigation.
  const isFiltered =
    !!(initialFilters.task_name ?? '') || statusValue !== STATUS_ALL || queueValue !== QUEUE_ALL;
  const filters: Filters = {
    status: statusValue,
    task_name: search,
    queue: queueValue,
  };

  // Work that is supposed to be moving. Counting `running` too is deliberate:
  // a row stuck in "running" with no worker alive means the worker died holding
  // it, which is exactly as wrong as an unattended queue.
  const backlog =
    (statusCounts?.[TASK_STATUS.PENDING] ?? 0) + (statusCounts?.[TASK_STATUS.RUNNING] ?? 0);

  // Set right before an explicit clear resets `search`, so the debounce
  // effect below — which would otherwise see `search` change and reschedule
  // a navigation using the still-stale filter props — skips that one run
  // instead of re-applying the filters `clearFilters` just cleared.
  const skipNextDebounceRef = useRef(false);

  function clearFilters() {
    // Only arm the skip when resetting `search` will actually fire the
    // effect — if the box is already empty the effect never runs for the
    // clear, and an armed flag would swallow the user's next keystroke.
    if (search !== '') skipNextDebounceRef.current = true;
    setSearch('');
    pushFilters({ status: STATUS_ALL, task_name: '', queue: QUEUE_ALL }, 1);
  }

  // Debounce search: any change from the server-provided value kicks off a
  // page-1 navigation 300ms after the user stops typing.
  useEffect(() => {
    if (skipNextDebounceRef.current) {
      skipNextDebounceRef.current = false;
      return;
    }
    if (search === (initialFilters.task_name ?? '')) return;
    const timeout = setTimeout(
      () => pushFilters({ status: statusValue, task_name: search, queue: queueValue }, 1),
      300,
    );
    return () => clearTimeout(timeout);
  }, [search, initialFilters.task_name, statusValue, queueValue]);

  async function handleRetry() {
    if (!retryTarget) return;
    setBusy(true);
    const created = await retryExecution(retryTarget);
    setBusy(false);
    setRetryTarget(null);
    if (created) router.reload({ only: RELOAD_ONLY });
  }

  async function handleRetryAll() {
    setBusy(true);
    const queued = await retryAllFailed({
      status: statusValue,
      taskName: initialFilters.task_name ?? '',
      queue: queueValue,
    });
    setBusy(false);
    setRetryAllOpen(false);
    if (queued !== null) router.reload({ only: RELOAD_ONLY });
  }

  return (
    <>
      <Head title={t(keys.background_tasks.index.title)} />
      <PageShell
        title={t(keys.background_tasks.index.title)}
        description={t(keys.background_tasks.index.description)}
        actions={
          <>
            <Button variant="outline" asChild className="max-lg:min-h-11">
              <Link href={`${VIEW_BASE}/workers`}>
                <ServerCog aria-hidden="true" />
                {t(keys.background_tasks.index.workers_button)}
              </Link>
            </Button>
            {canRetry && (
              <Button
                variant="outline"
                className="max-lg:min-h-11"
                onClick={() => setRetryAllOpen(true)}
              >
                <RefreshCcw aria-hidden="true" />
                {t(keys.background_tasks.index.retry_all_button)}
              </Button>
            )}
          </>
        }
      >
        <StatusStrip
          counts={statusCounts ?? {}}
          active={initialFilters.status ?? ''}
          onSelect={(status) => pushFilters({ ...filters, status }, 1)}
        />

        {/* `statusCounts` (and therefore `backlog`) is scoped to the active
            filters — a narrowed view can read zero backlog while the real
            fleet-wide queue is still stuck, so only trust it as a health
            signal when nothing is filtering it. Undrawn in the deck; it only
            appears when a backlog has nobody to work it. */}
        {!isFiltered && <WorkerHealthBanner backlog={backlog} />}

        <TaskFilters
          search={search}
          onSearchChange={setSearch}
          status={statusValue}
          onStatusChange={(status) => pushFilters({ ...filters, status }, 1)}
          queue={queueValue}
          onQueueChange={(queue) => pushFilters({ ...filters, queue }, 1)}
          queues={queues ?? []}
        />

        <ExecutionsTable
          executions={executions}
          canRetry={canRetry}
          onRetry={setRetryTarget}
          page={pagination.page}
          perPage={pagination.per_page}
          total={pagination.total}
          onPageChange={(page) => pushFilters(filters, page)}
          empty={
            <TasksEmptyRow
              filtered={isFiltered}
              columnCount={COLUMN_COUNT}
              presence={workerPresence ?? null}
              onClear={clearFilters}
            />
          }
        />

        <RetryConfirmDialog
          target={retryTarget}
          onOpenChange={(open) => !open && setRetryTarget(null)}
          onConfirm={handleRetry}
          busy={busy}
        />
        <RetryAllDialog
          open={retryAllOpen}
          onOpenChange={setRetryAllOpen}
          onConfirm={handleRetryAll}
          busy={busy}
          status={statusValue}
          taskName={initialFilters.task_name ?? ''}
          queue={queueValue}
        />
      </PageShell>
    </>
  );
}

Index.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Index;
