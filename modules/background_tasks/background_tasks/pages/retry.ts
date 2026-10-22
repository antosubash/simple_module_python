// Shared retry plumbing for the Index and Detail pages. Both POST to the
// same endpoint; they differ only in what they do with the result (reload
// the list vs. navigate to the new row), so the fetch + toast live here.

import { keys, t } from '@simple-module-py/i18n';
import { apiResult } from '@simple-module-py/ui/lib/api';
import { toast } from 'sonner';
import { api } from './api';
import { QUEUE_ALL, STATUS_ALL, type TaskStatus, TENANT_ALL } from './constants';

export interface Execution {
  id: string;
  celery_task_id: string | null;
  task_name: string;
  status: TaskStatus;
  queue: string;
  /** Tenant that published the task; null for beat / platform publishes. */
  tenant_id: string | null;
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

const inFlight = new Map<string, Promise<Execution | null>>();

/**
 * Re-enqueue one execution. Clicks that land while a retry for the same row is
 * still in flight share its request: the dialog's `busy` state only disables the
 * button after a re-render, so a burst of clicks would otherwise each POST.
 * Retrying a row again *after* the first retry settles stays allowed.
 */
export function retryExecution(execution: {
  id: string;
  task_name: string;
}): Promise<Execution | null> {
  const pending = inFlight.get(execution.id);
  if (pending) return pending;
  const request = postRetry(execution).finally(() => inFlight.delete(execution.id));
  inFlight.set(execution.id, request);
  return request;
}

async function postRetry(execution: { id: string; task_name: string }): Promise<Execution | null> {
  const result = await apiResult(
    api.POST('/api/background_tasks/admin/executions/{execution_id}/retry', {
      params: { path: { execution_id: execution.id } },
    }),
  );
  if (!result.ok) {
    toast.error(result.detail ?? t(keys.background_tasks.toasts.retry_failed));
    return null;
  }
  // Called, not captured at module scope, so it reads the live locale.
  toast.success(t(keys.background_tasks.toasts.retried, { name: execution.task_name }));
  return result.data as Execution;
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
  tenant: string;
}): Promise<number | null> {
  const result = await apiResult(
    api.POST('/api/background_tasks/admin/executions/retry-failed', {
      params: {
        query: {
          status:
            filters.status && filters.status !== STATUS_ALL
              ? (filters.status as TaskStatus)
              : undefined,
          q: filters.taskName || undefined,
          queue: filters.queue && filters.queue !== QUEUE_ALL ? filters.queue : undefined,
          tenant_id: filters.tenant && filters.tenant !== TENANT_ALL ? filters.tenant : undefined,
        },
      },
    }),
  );
  if (!result.ok) {
    toast.error(result.detail ?? t(keys.background_tasks.toasts.bulk_retry_failed));
    return null;
  }
  const { queued, remaining } = result.data;
  toast.success(t(keys.background_tasks.toasts.bulk_retried, { count: queued }), {
    description:
      remaining > 0
        ? t(keys.background_tasks.toasts.bulk_remaining, { count: remaining })
        : undefined,
  });
  return queued;
}
