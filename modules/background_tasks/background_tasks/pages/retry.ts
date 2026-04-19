// Shared retry plumbing for the Index and Detail pages. Both POST to the
// same endpoint; they differ only in what they do with the result (reload
// the list vs. navigate to the new row), so the fetch + toast live here.

import { fetchWithCsrf } from '@simple-module/ui/lib/csrf';
import { toast } from 'sonner';
import { API_BASE, type TaskStatus } from './constants';

export interface Execution {
  id: string;
  celery_task_id: string | null;
  task_name: string;
  status: TaskStatus;
  queue: string;
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
    const res = await fetchWithCsrf(`${API_BASE}/executions/${execution.id}/retry`, {
      method: 'POST',
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    const created = (await res.json()) as Execution;
    toast.success(`Task "${execution.task_name}" re-enqueued`);
    return created;
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Failed to retry task');
    return null;
  }
}
