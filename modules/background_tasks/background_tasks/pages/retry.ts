// Shared retry plumbing for the Index and Detail pages. Both POST to the
// same endpoint; they differ only in what they do with the result (reload
// the list vs. navigate to the new row), so the fetch + toast live here.

import { keys, t } from '@simple-module-py/i18n';
import { toast } from 'sonner';
import { API_BASE, QUEUE_ALL, STATUS_ALL, type TaskStatus } from './constants';

export interface Execution {
  id: string;
  celery_task_id: string | null;
  task_name: string;
  status: TaskStatus;
  queue: string;
  // Shown by the retry confirm before it re-enqueues them — see the list schema.
  args: unknown[];
  kwargs: Record<string, unknown>;
  retries: number;
  worker: string | null;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  exception_type: string | null;
  retried_from_id: string | null;
}

export async function retryExecution(execution: {
  id: string;
  task_name: string;
}): Promise<Execution | null> {
  try {
    const res = await fetch(`${API_BASE}/executions/${execution.id}/retry`, {
      method: 'POST',
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    const created = (await res.json()) as Execution;
    // Called, not captured at module scope, so it reads the live locale.
    toast.success(t(keys.background_tasks.toasts.retried, { name: execution.task_name }));
    return created;
  } catch (err) {
    toast.error(err instanceof Error ? err.message : t(keys.background_tasks.toasts.retry_failed));
    return null;
  }
}

/**
 * Re-enqueue the failed and stuck executions the current filters can see.
 *
 * The filters go to the server rather than being resolved here: the client
 * only knows the twenty rows on this page, and the operator pressing "Retry
 * all failed" means every matching row, not every visible one. All three axes
 * travel — status, search and queue — so the sweep covers exactly the rows on
 * screen.
 *
 * Returns how many were queued, or `null` if the request failed. The server
 * caps one pass, so `remaining` may be non-zero; the toast says so rather than
 * leaving the operator to wonder why the backlog only half moved.
 */
export async function retryAllFailed(filters: {
  status: string;
  taskName: string;
  queue: string;
}): Promise<number | null> {
  const params = new URLSearchParams();
  if (filters.status && filters.status !== STATUS_ALL) params.set('status', filters.status);
  if (filters.taskName) params.set('q', filters.taskName);
  if (filters.queue && filters.queue !== QUEUE_ALL) params.set('queue', filters.queue);
  const query = params.toString();
  try {
    const res = await fetch(`${API_BASE}/executions/retry-failed${query ? `?${query}` : ''}`, {
      method: 'POST',
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    const { queued, remaining } = (await res.json()) as { queued: number; remaining: number };
    toast.success(t(keys.background_tasks.toasts.bulk_retried, { count: queued }), {
      description:
        remaining > 0
          ? t(keys.background_tasks.toasts.bulk_remaining, { count: remaining })
          : undefined,
    });
    return queued;
  } catch (err) {
    toast.error(
      err instanceof Error ? err.message : t(keys.background_tasks.toasts.bulk_retry_failed),
    );
    return null;
  }
}
