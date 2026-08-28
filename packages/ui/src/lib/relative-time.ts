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

export const RELATIVE_AGE_KEYS = {
  unknown: 'ui.relative_time.unknown',
  justNow: 'ui.relative_time.just_now',
  seconds: 'ui.relative_time.seconds_ago',
  minutes: 'ui.relative_time.minutes_ago',
  hours: 'ui.relative_time.hours_ago',
} as const;

export type RelativeAgeKey = (typeof RELATIVE_AGE_KEYS)[keyof typeof RELATIVE_AGE_KEYS];

/**
 * Which bucket an age falls into, and the number to put in the sentence.
 *
 * The wording itself lives in the ui catalog: this returns a key rather than a
 * finished string so the caller translates it with its own `t`. Bucketing is
 * what is worth testing, and it stays a pure function.
 */
export interface RelativeAge {
  key: RelativeAgeKey;
  count?: number;
}

export function relativeAge(ageMs: number): RelativeAge {
  if (!Number.isFinite(ageMs)) return { key: RELATIVE_AGE_KEYS.unknown };
  const age = Math.max(0, ageMs);
  if (age < 10 * SECOND) return { key: RELATIVE_AGE_KEYS.justNow };
  if (age < MINUTE) return { key: RELATIVE_AGE_KEYS.seconds, count: Math.floor(age / SECOND) };
  if (age < HOUR) return { key: RELATIVE_AGE_KEYS.minutes, count: Math.floor(age / MINUTE) };
  return { key: RELATIVE_AGE_KEYS.hours, count: Math.floor(age / HOUR) };
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
