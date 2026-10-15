// Types and API calls for the durable-event outbox page (GH #459).

import { keys, t } from '@simple-module-py/i18n';
import { toast } from 'sonner';
import { API_BASE } from './constants';

export const OUTBOX_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  DELIVERED: 'delivered',
  DEAD: 'dead',
} as const;

export type OutboxStatus = (typeof OUTBOX_STATUS)[keyof typeof OUTBOX_STATUS];

/** The statuses the page lists — delivered rows only wait for the purge. */
export const OPEN_OUTBOX_STATUSES = [
  OUTBOX_STATUS.PENDING,
  OUTBOX_STATUS.RUNNING,
  OUTBOX_STATUS.DEAD,
] as const;

export const OUTBOX_STATUS_LABEL_KEY = {
  [OUTBOX_STATUS.PENDING]: keys.background_tasks.outbox.status_pending,
  [OUTBOX_STATUS.RUNNING]: keys.background_tasks.outbox.status_running,
  [OUTBOX_STATUS.DELIVERED]: keys.background_tasks.outbox.status_delivered,
  [OUTBOX_STATUS.DEAD]: keys.background_tasks.outbox.status_dead,
} as const;

export const OUTBOX_PILL_CLASS: Record<OutboxStatus, string> = {
  [OUTBOX_STATUS.PENDING]: 'text-muted-foreground bg-secondary',
  [OUTBOX_STATUS.RUNNING]: 'text-blue-700 bg-blue-50',
  [OUTBOX_STATUS.DELIVERED]: 'text-primary-700 bg-primary-600/10',
  [OUTBOX_STATUS.DEAD]: 'text-red-700 bg-red-50',
};

export interface OutboxMessage {
  id: string;
  event_key: string;
  handler_name: string;
  payload: Record<string, unknown>;
  tenant_id: string | null;
  status: OutboxStatus;
  attempts: number;
  next_attempt_at: string;
  locked_until: string | null;
  last_error: string | null;
  created_at: string;
  delivered_at: string | null;
}

const OUTBOX_API = `${API_BASE}/outbox`;

async function send(url: string, method: string): Promise<void> {
  const res = await fetch(url, { method, headers: { Accept: 'application/json' } });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${res.status}`);
  }
}

/** Send a dead message round again from attempt 1. Resolves true on success. */
export async function retryOutboxMessage(id: string): Promise<boolean> {
  try {
    await send(`${OUTBOX_API}/${id}/retry`, 'POST');
    toast.success(t(keys.background_tasks.outbox.retried));
    return true;
  } catch (err) {
    toast.error(err instanceof Error ? err.message : t(keys.background_tasks.outbox.retry_failed));
    return false;
  }
}

/** Drop a pending or dead message without delivering it. */
export async function discardOutboxMessage(id: string): Promise<boolean> {
  try {
    await send(`${OUTBOX_API}/${id}`, 'DELETE');
    toast.success(t(keys.background_tasks.outbox.discarded));
    return true;
  } catch (err) {
    toast.error(
      err instanceof Error ? err.message : t(keys.background_tasks.outbox.discard_failed),
    );
    return false;
  }
}

/** `orders.contracts.events.OrderPlaced` → `OrderPlaced`, the part people recognise. */
export function shortName(dotted: string): string {
  const parts = dotted.split('.');
  return parts[parts.length - 1] || dotted;
}
