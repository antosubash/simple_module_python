// Frontend mirror of background_tasks/constants.py.
// Kept small and hand-maintained — the backend file is the source of truth.

import { keys } from '@simple-module-py/i18n';

export const API_BASE = '/api/background_tasks/admin';
export const VIEW_BASE = '/admin/background-tasks';

export function formatTs(ts: string | null): string {
  return ts ? new Date(ts).toLocaleString() : '—';
}

export interface WorkerInfo {
  hostname: string;
  online: boolean;
  queues: string[];
  active_task_count: number;
  pool_size: number | null;
  total_processed: number | null;
  software: string | null;
}

export interface WorkerSnapshot {
  broker_reachable: boolean;
  polled_at: string;
  workers: WorkerInfo[];
  error: string | null;
}

export const TASK_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  SUCCESS: 'success',
  FAILED: 'failed',
  STUCK: 'stuck',
  REVOKED: 'revoked',
  RETRYING: 'retrying',
} as const;

export type TaskStatus = (typeof TASK_STATUS)[keyof typeof TASK_STATUS];

export const RETRYABLE_STATUSES: ReadonlySet<TaskStatus> = new Set([
  TASK_STATUS.FAILED,
  TASK_STATUS.STUCK,
]);

export const TERMINAL_STATUSES: ReadonlySet<TaskStatus> = new Set([
  TASK_STATUS.SUCCESS,
  TASK_STATUS.FAILED,
  TASK_STATUS.STUCK,
  TASK_STATUS.REVOKED,
]);

export const STATUS_BADGE_VARIANT: Record<TaskStatus, 'secondary' | 'destructive' | 'outline'> = {
  [TASK_STATUS.PENDING]: 'outline',
  [TASK_STATUS.RUNNING]: 'secondary',
  [TASK_STATUS.SUCCESS]: 'secondary',
  [TASK_STATUS.FAILED]: 'destructive',
  [TASK_STATUS.STUCK]: 'destructive',
  [TASK_STATUS.REVOKED]: 'outline',
  [TASK_STATUS.RETRYING]: 'outline',
};

/**
 * Catalog key per status. The label used to be the raw status string with its
 * first letter capitalised, which cannot be translated — and capitalisation is
 * not a universal way to make a word into a label anyway.
 */
export const STATUS_LABEL_KEY = {
  [TASK_STATUS.PENDING]: keys.background_tasks.status.pending,
  [TASK_STATUS.RUNNING]: keys.background_tasks.status.running,
  [TASK_STATUS.SUCCESS]: keys.background_tasks.status.success,
  [TASK_STATUS.FAILED]: keys.background_tasks.status.failed,
  [TASK_STATUS.STUCK]: keys.background_tasks.status.stuck,
  [TASK_STATUS.REVOKED]: keys.background_tasks.status.revoked,
  [TASK_STATUS.RETRYING]: keys.background_tasks.status.retrying,
} as const;

export const STATUS_ORDER: TaskStatus[] = [
  TASK_STATUS.PENDING,
  TASK_STATUS.RUNNING,
  TASK_STATUS.RETRYING,
  TASK_STATUS.SUCCESS,
  TASK_STATUS.FAILED,
  TASK_STATUS.STUCK,
  TASK_STATUS.REVOKED,
];
