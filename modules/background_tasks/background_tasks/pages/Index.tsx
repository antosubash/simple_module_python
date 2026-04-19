import { router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card } from '@simple-module/ui/components/ui/card';
import { Input } from '@simple-module/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module/ui/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module/ui/components/ui/table';
import { usePermissions } from '@simple-module/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { fetchWithCsrf } from '@simple-module/ui/lib/csrf';
import { Activity, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { type Execution, ExecutionRow, statusLabel } from './components/ExecutionRow';
import { API_BASE, STATUS_ORDER, VIEW_BASE } from './constants';

interface Pagination {
  page: number;
  per_page: number;
  total: number;
}

interface Filters {
  status: string;
  task_name: string;
}

interface Props {
  executions: Execution[];
  pagination: Pagination;
  filters: Filters;
}

const STATUS_ALL = '__all__';

function Index() {
  const {
    executions,
    pagination,
    filters: initialFilters,
  } = usePage<{ props: Props }>().props as unknown as Props;

  const { can } = usePermissions();
  const canRetry = can('background_tasks.manage');

  const [search, setSearch] = useState(initialFilters.task_name ?? '');
  const [status, setStatus] = useState<string>(initialFilters.status || STATUS_ALL);

  const totalPages = useMemo(
    () => Math.ceil(pagination.total / pagination.per_page),
    [pagination.total, pagination.per_page],
  );

  const navigate = useCallback(
    (opts: { page?: number; q?: string; status?: string }) => {
      const params: Record<string, string> = {};
      const q = opts.q ?? search;
      const s = opts.status ?? status;
      const page = opts.page ?? 1;
      if (q) params.q = q;
      if (s && s !== STATUS_ALL) params.status = s;
      if (page > 1) params.page = String(page);
      router.get(VIEW_BASE, params, { preserveState: true, preserveScroll: true });
    },
    [search, status],
  );

  useEffect(() => {
    if (search === (initialFilters.task_name ?? '')) return;
    const timeout = setTimeout(() => navigate({ q: search }), 300);
    return () => clearTimeout(timeout);
  }, [search, initialFilters.task_name, navigate]);

  async function handleRetry(execution: Execution) {
    try {
      const res = await fetchWithCsrf(`${API_BASE}/executions/${execution.id}/retry`, {
        method: 'POST',
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      toast.success(`Task "${execution.task_name}" re-enqueued`);
      router.reload({ only: ['executions', 'pagination'] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to retry task');
    }
  }

  return (
    <PageShell
      title="Background Tasks"
      description="Monitor task executions and retry failed or stuck jobs."
    >
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
        <Select
          value={status}
          onValueChange={(v) => {
            setStatus(v);
            navigate({ status: v, page: 1 });
          }}
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
              <TableRow>
                <TableCell colSpan={7} className="h-32 text-center">
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <Activity className="size-8" />
                    <p>
                      {search
                        ? `No tasks match "${search}"`
                        : 'No task executions yet. Tasks appear here as soon as modules enqueue work.'}
                    </p>
                  </div>
                </TableCell>
              </TableRow>
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
            onClick={() => navigate({ page: pagination.page - 1 })}
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
            onClick={() => navigate({ page: pagination.page + 1 })}
          >
            Next
          </Button>
        </div>
      )}
    </PageShell>
  );
}

Index.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Index;
