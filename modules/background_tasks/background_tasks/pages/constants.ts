// Frontend mirror of background_tasks/constants.py.
// Kept small and hand-maintained — the backend file is the source of truth.

import { keys } from '@simple-module-py/i18n';
import { formatDayMonthTime } from '@simple-module-py/ui/lib/date-format';

export const API_BASE = '/api/background_tasks/admin';
export const VIEW_BASE = '/admin/background-tasks';

/** Rendered wherever a value is genuinely absent, so the columns still line up. */
export const EM_DASH = '—';

/**
 * "19 Aug 14:02:11" — the same shape the audit log uses.
 *
 * The deck shows time only, which is unreadable the moment a row is older than
 * today: "09:41:02" on a three-day-old execution invites the reader to assume
 * this morning. The date costs four characters and removes the guess.
 *
 * Fixed rather than locale-dependent: the reader's locale gave "Sep 3,
 * 08:48:40", which is a different order and a comma away from every other
 * timestamp in the product. See `ui/lib/date-format`.
 */
export function formatTs(ts: string | null): string {
  if (!ts) return EM_DASH;
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return EM_DASH;
  return formatDayMonthTime(ts);
}

/** "09:44:10" — a reading taken moments ago needs no date. */
export function formatClock(ts: string | null): string {
  if (!ts) return EM_DASH;
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) return EM_DASH;
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(parsed);
}

/**
 * How long a run took, or a dash while it is still taking it.
 *
 * A live-ticking elapsed time on a running row reads as a measurement, and an
 * operator comparing it against the finished rows beside it is comparing a
 * duration with a stopwatch. Unfinished work has no duration yet.
 */
export function formatDuration(started: string | null, finished: string | null): string {
  if (!started || !finished) return EM_DASH;
  const ms = new Date(finished).getTime() - new Date(started).getTime();
  if (!Number.isFinite(ms) || ms < 0) return EM_DASH;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`;
}

/** "4d 2h" — coarse on purpose; nobody reads a worker's uptime to the second. */
export function formatUptime(seconds: number | null): string | null {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return null;
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${Math.floor(seconds)}s`;
}

/**
 * "py-celery:5.4.0" → "celery 5.4.0".
 *
 * The wire format is Celery's own `sw_ident:sw_ver`; the "py-" prefix
 * distinguishes the Python implementation from other language ports, which is
 * not a distinction anyone reading this page is making.
 */
export function formatSoftware(software: string | null): string | null {
  if (!software) return null;
  const [ident, version] = software.split(':');
  const name = ident.replace(/^py-/, '');
  return version ? `${name} ${version}` : name;
}

/**
 * The detail page's row — `TaskExecutionDetail` from the backend.
 *
 * A superset of the list item (`Execution` in `retry.ts`): the extra fields
 * are the ones only worth shipping for a single row.
 */
export interface TaskDetail {
  id: string;
  celery_task_id: string | null;
  task_name: string;
  status: TaskStatus;
  queue: string;
  args: unknown[];
  kwargs: Record<string, unknown>;
  result: Record<string, unknown> | null;
  traceback: string | null;
  exception_type: string | null;
  worker: string | null;
  retries: number;
  retried_from_id: string | null;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  heartbeat_at: string | null;
}

export interface WorkerInfo {
  hostname: string;
  online: boolean;
  queues: string[];
  active_task_count: number;
  pool_size: number | null;
  total_processed: number | null;
  software: string | null;
  uptime_seconds: number | null;
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

/**
 * Borderless tint per status, keyed by what the status means rather than by
 * a palette ramp: red is "someone must act", amber "this is not moving", blue
 * "in flight", emerald "done", grey "nothing to say".
 */
export const STATUS_PILL_CLASS: Record<TaskStatus, string> = {
  [TASK_STATUS.PENDING]: 'text-muted-foreground bg-secondary',
  [TASK_STATUS.RUNNING]: 'text-blue-700 bg-blue-50',
  [TASK_STATUS.SUCCESS]: 'text-primary-700 bg-primary-600/10',
  [TASK_STATUS.FAILED]: 'text-red-700 bg-red-50',
  [TASK_STATUS.STUCK]: 'text-amber-700 bg-amber-50',
  [TASK_STATUS.REVOKED]: 'text-muted-foreground bg-secondary',
  [TASK_STATUS.RETRYING]: 'text-amber-700 bg-amber-50',
};

/**
 * Catalog key per status. The label used to be the raw status string with its
 * first letter capitalised, which cannot be translated — and capitalisation is
 * not a universal way to make a word into a label anyway.
 */
export const STATUS_LABEL_KEY = {
  // "queued", not "pending": the tile above the table is labelled Queued, and
  // one state should not have two names on one screen. The stored enum value
  // stays `pending` — it is a wire format, not copy.
  [TASK_STATUS.PENDING]: keys.background_tasks.status.queued,
  [TASK_STATUS.RUNNING]: keys.background_tasks.status.running,
  [TASK_STATUS.SUCCESS]: keys.background_tasks.status.success,
  [TASK_STATUS.FAILED]: keys.background_tasks.status.failed,
  [TASK_STATUS.STUCK]: keys.background_tasks.status.stuck,
  [TASK_STATUS.REVOKED]: keys.background_tasks.status.revoked,
  [TASK_STATUS.RETRYING]: keys.background_tasks.status.retrying,
} as const;

/** Sentinel for "no status filter"; an empty string cannot be a Select value. */
export const STATUS_ALL = 'all';
/**
 * Same, for the queue dropdown — but underscored, because queue names are
 * whatever a module chose and one of them could legitimately be called "all".
 */
export const QUEUE_ALL = '__all__';

/**
 * The four the segmented control offers: everything, plus the three states an
 * operator triages. `pending`, `success`, `revoked` and `retrying` stay
 * reachable through the stat tiles, which is where a whole-fleet number
 * belongs anyway.
 */
export const SEGMENT_STATUSES = [
  STATUS_ALL,
  TASK_STATUS.FAILED,
  TASK_STATUS.RUNNING,
  TASK_STATUS.STUCK,
] as const;

export const SEGMENT_LABEL_KEY = {
  [STATUS_ALL]: keys.background_tasks.filters.all,
  [TASK_STATUS.FAILED]: keys.background_tasks.filters.failed,
  [TASK_STATUS.RUNNING]: keys.background_tasks.filters.running,
  [TASK_STATUS.STUCK]: keys.background_tasks.filters.stuck,
} as const;

/**
 * A task payload on one line: `[ "a91f2c" ]`, `{ "size": 512 }`.
 *
 * Indent-1 JSON with the newlines collapsed, rather than a bare
 * `JSON.stringify`, because the spaces are what make a nested payload
 * skimmable at a glance — and skimming it is the entire reason it is shown
 * next to a retry button.
 */
export function formatPayload(value: unknown): string {
  try {
    return JSON.stringify(value, null, 1)?.replace(/\n\s*/g, ' ') ?? String(value);
  } catch {
    return UNSERIALISABLE;
  }
}

/**
 * The same payload with the braces closed up: `{"size": 512}`.
 *
 * The retry dialog's box is one line inside a modal, where the deck tightens
 * the brackets but keeps the space after each colon — that space is what
 * stops `{"size":512}` reading as one token. `formatPayload` above is the
 * roomier form the detail page's own cards use.
 */
export function formatCompactPayload(value: unknown): string {
  try {
    const json = JSON.stringify(value, null, 1);
    if (json === undefined) return String(value);
    return json.replace(/\n\s*/g, '').replace(/,(?=\S)/g, ', ');
  } catch {
    return UNSERIALISABLE;
  }
}

/** Shown instead of a payload that cannot be stringified (a cycle, a BigInt). */
export const UNSERIALISABLE = '<unserialisable>';

/** `c1a4…8de2` — enough of an id to recognise, not enough to read aloud. */
export function shortenId(id: string): string {
  return id.length <= 12 ? id : `${id.slice(0, 4)}…${id.slice(-4)}`;
}
