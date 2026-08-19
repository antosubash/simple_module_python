/**
 * Age of a polled snapshot, in words.
 *
 * A page that shows a point-in-time reading and only refreshes on demand looks
 * exactly the same after ten seconds and after an hour. An absolute timestamp
 * does not fix that — the reader has to subtract it from the current time to
 * notice. Saying how *old* the reading is puts the staleness in the sentence.
 */

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;

/** Past this, a snapshot is old enough that it may no longer describe reality. */
export const STALE_AFTER_MS = 60 * SECOND;

export function relativeAgeLabel(ageMs: number): string {
  if (!Number.isFinite(ageMs)) return 'unknown';
  const age = Math.max(0, ageMs);
  if (age < 10 * SECOND) return 'just now';
  if (age < MINUTE) return `${Math.floor(age / SECOND)}s ago`;
  if (age < HOUR) return `${Math.floor(age / MINUTE)}m ago`;
  return `${Math.floor(age / HOUR)}h ago`;
}

export function isStale(ageMs: number): boolean {
  return Number.isFinite(ageMs) && ageMs >= STALE_AFTER_MS;
}

/**
 * Milliseconds between `now` and an ISO timestamp, or NaN if it cannot be read.
 * Clamped at zero: a server clock a little ahead of the browser's should read
 * as "just now", never as a negative age.
 */
export function ageOf(isoTimestamp: string | null | undefined, now: number): number {
  if (!isoTimestamp) return Number.NaN;
  const parsed = new Date(isoTimestamp).getTime();
  if (Number.isNaN(parsed)) return Number.NaN;
  return Math.max(0, now - parsed);
}
