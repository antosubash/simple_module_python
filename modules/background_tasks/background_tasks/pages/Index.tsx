import { Head, Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Search, ServerCog } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ExecutionRow, statusLabel } from './components/ExecutionRow';
import { type StatusCounts, StatusStrip } from './components/StatusStrip';
import { TasksEmptyRow, type WorkerPresence } from './components/TasksEmpty';
import { WorkerHealthBanner } from './components/WorkerHealthBanner';
import { STATUS_ORDER, TASK_STATUS, VIEW_BASE } from './constants';
import { type Execution, retryExecution } from './retry';

interface Pagination {
  page: number;
  per_page: number;
  total: number;
}

interface Props {
  executions: Execution[];
  pagination: Pagination;
  filters: { status: string; task_name: string };
  status_counts: StatusCounts;
  /** Null unless the unfiltered list came back empty — see the index view. */
  worker_presence: WorkerPresence | null;
}

/** Task, Status, Queue, Queued, Duration, Worker, Actions. */
const COLUMN_COUNT = 7;

const STATUS_ALL = '__all__';

function pushFilters(filters: { status: string; task_name: string }, page: number): void {
  const params: Record<string, string> = {};
  if (filters.task_name) params.q = filters.task_name;
  if (filters.status && filters.status !== STATUS_ALL) params.status = filters.status;
  if (page > 1) params.page = String(page);
  router.get(VIEW_BASE, params, { preserveState: true, preserveScroll: true });
}

function Index() {
  const {
    executions,
    pagination,
    filters: initialFilters,
    status_counts: statusCounts,
    worker_presence: workerPresence,
  } = usePage<{ props: Props }>().props as unknown as Props;

  const { can } = usePermissions();
  const canRetry = can('background_tasks.manage');

  const [search, setSearch] = useState(initialFilters.task_name ?? '');
  const totalPages = Math.ceil(pagination.total / pagination.per_page);
  const statusValue = initialFilters.status || STATUS_ALL;
  // Derived from the server-confirmed filters, not the live `search` input:
  // `workerPresence` reflects the last committed request, so mixing it with
  // unsubmitted local state would flash the wrong empty-state copy during the
  // debounce window between a keystroke and the resulting navigation.
  const isFiltered = !!(initialFilters.task_name ?? '') || statusValue !== STATUS_ALL;

  // Work that is supposed to be moving. Counting `running` too is deliberate:
  // a row stuck in "running" with no worker alive means the worker died holding
  // it, which is exactly as wrong as an unattended queue.
  const backlog =
    (statusCounts?.[TASK_STATUS.PENDING] ?? 0) + (statusCounts?.[TASK_STATUS.RUNNING] ?? 0);

  function clearFilters() {
    setSearch('');
    pushFilters({ status: STATUS_ALL, task_name: '' }, 1);
  }

  // Debounce search: any change from the server-provided value kicks off a
  // page-1 navigation 300ms after the user stops typing.
  useEffect(() => {
    if (search === (initialFilters.task_name ?? '')) return;
    const timeout = setTimeout(
      () => pushFilters({ status: statusValue, task_name: search }, 1),
      300,
    );
    return () => clearTimeout(timeout);
  }, [search, initialFilters.task_name, statusValue]);

  async function handleRetry(execution: Execution) {
    const created = await retryExecution(execution);
    // status_counts feeds the strip above the table — a retry moves a row out
    // of "failed", so leaving it out of the reload leaves the tile lying.
    if (created) router.reload({ only: ['executions', 'pagination', 'status_counts'] });
  }

  return (
    <>
      <Head title="Background Tasks" />
      <PageShell
        title="Background Tasks"
        description="Monitor task executions and retry failed or stuck jobs."
      >
        <StatusStrip
          counts={statusCounts ?? {}}
          active={initialFilters.status ?? ''}
          onSelect={(status) => pushFilters({ status, task_name: search }, 1)}
        />

        <WorkerHealthBanner backlog={backlog} />

        <div className="mb-4 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
            <Input
              placeholder="Search by task name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <div className="flex items-center gap-2">
            <Select
              value={statusValue}
              onValueChange={(v) => pushFilters({ status: v, task_name: search }, 1)}
            >
              <SelectTrigger className="w-full sm:w-48">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={STATUS_ALL}>All statuses</SelectItem>
                {STATUS_ORDER.map((s) => (
                  <SelectItem key={s} value={s}>
                    {statusLabel(s)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" asChild>
              <Link href={`${VIEW_BASE}/workers`}>
                <ServerCog className="mr-2 size-4" />
                Workers
              </Link>
            </Button>
          </div>
        </div>

        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Task</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden md:table-cell">Queue</TableHead>
                <TableHead className="hidden lg:table-cell">Queued</TableHead>
                <TableHead className="hidden sm:table-cell">Duration</TableHead>
                <TableHead className="hidden xl:table-cell">Worker</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {executions.map((e) => (
                <ExecutionRow key={e.id} execution={e} canRetry={canRetry} onRetry={handleRetry} />
              ))}
              {executions.length === 0 && (
                <TasksEmptyRow
                  filtered={isFiltered}
                  columnCount={COLUMN_COUNT}
                  presence={workerPresence ?? null}
                  onClear={clearFilters}
                />
              )}
            </TableBody>
          </Table>
        </Card>

        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={pagination.page <= 1}
              onClick={() =>
                pushFilters({ status: statusValue, task_name: search }, pagination.page - 1)
              }
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {pagination.page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={pagination.page >= totalPages}
              onClick={() =>
                pushFilters({ status: statusValue, task_name: search }, pagination.page + 1)
              }
            >
              Next
            </Button>
          </div>
        )}
      </PageShell>
    </>
  );
}

Index.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Index;
