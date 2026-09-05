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
const DAY = 24 * HOUR;
const MONTH = 30 * DAY;
const YEAR = 365 * DAY;

/** Past this, a snapshot is old enough that it may no longer describe reality. */
export const STALE_AFTER_MS = 60 * SECOND;

export const RELATIVE_AGE_KEYS = {
  unknown: 'ui.relative_time.unknown',
  justNow: 'ui.relative_time.just_now',
  seconds: 'ui.relative_time.seconds_ago',
  minutes: 'ui.relative_time.minutes_ago',
  hours: 'ui.relative_time.hours_ago',
  days: 'ui.relative_time.days_ago',
  months: 'ui.relative_time.months_ago',
  years: 'ui.relative_time.years_ago',
} as const;

export type RelativeAgeKey = (typeof RELATIVE_AGE_KEYS)[keyof typeof RELATIVE_AGE_KEYS];

/**
 * The same idea pointed forwards: how long until a deadline, not how long
 * since a reading. Invitations and API keys expire, and "in 3d" answers the
 * only question a reader has about an expiry date.
 */
export const RELATIVE_UNTIL_KEYS = {
  minutes: 'ui.relative_time.in_minutes',
  hours: 'ui.relative_time.in_hours',
  days: 'ui.relative_time.in_days',
  expired: 'ui.relative_time.expired',
} as const;

export type RelativeUntilKey = (typeof RELATIVE_UNTIL_KEYS)[keyof typeof RELATIVE_UNTIL_KEYS];

/**
 * Which bucket an age falls into, and the number to put in the sentence.
 *
 * The wording itself lives in the ui catalog: this returns a key rather than a
 * finished string so the caller translates it with its own `t`. Bucketing is
 * what is worth testing, and it stays a pure function.
 */
export interface RelativeAge {
  key: RelativeAgeKey | RelativeUntilKey;
  count?: number;
}

export function relativeAge(ageMs: number): RelativeAge {
  if (!Number.isFinite(ageMs)) return { key: RELATIVE_AGE_KEYS.unknown };
  const age = Math.max(0, ageMs);
  if (age < 10 * SECOND) return { key: RELATIVE_AGE_KEYS.justNow };
  if (age < MINUTE) return { key: RELATIVE_AGE_KEYS.seconds, count: Math.floor(age / SECOND) };
  if (age < HOUR) return { key: RELATIVE_AGE_KEYS.minutes, count: Math.floor(age / MINUTE) };
  if (age < DAY) return { key: RELATIVE_AGE_KEYS.hours, count: Math.floor(age / HOUR) };
  if (age < MONTH) return { key: RELATIVE_AGE_KEYS.days, count: Math.floor(age / DAY) };
  if (age < YEAR) return { key: RELATIVE_AGE_KEYS.months, count: Math.floor(age / MONTH) };
  return { key: RELATIVE_AGE_KEYS.years, count: Math.floor(age / YEAR) };
}

/**
 * Which bucket a remaining lifetime falls into.
 *
 * Anything at or past its deadline reads as expired rather than as a negative
 * countdown, and a sub-minute remainder rounds *up* — "in 0m" would read as
 * already gone when there is still time to act.
 */
export function relativeUntil(msUntil: number): RelativeAge {
  if (!Number.isFinite(msUntil)) return { key: RELATIVE_AGE_KEYS.unknown };
  if (msUntil <= 0) return { key: RELATIVE_UNTIL_KEYS.expired };
  if (msUntil < HOUR) {
    return { key: RELATIVE_UNTIL_KEYS.minutes, count: Math.max(1, Math.floor(msUntil / MINUTE)) };
  }
  if (msUntil < DAY) return { key: RELATIVE_UNTIL_KEYS.hours, count: Math.floor(msUntil / HOUR) };
  return { key: RELATIVE_UNTIL_KEYS.days, count: Math.floor(msUntil / DAY) };
}

export function isStale(ageMs: number): boolean {
  return Number.isFinite(ageMs) && ageMs >= STALE_AFTER_MS;
}

/**
 * Epoch milliseconds for an ISO timestamp, or NaN for anything unreadable —
 * missing, empty, or not a date. The one place that decides what "unreadable"
 * means, so `ageOf` and `timeUntil` cannot drift apart on the edge cases.
 */
function parseTimestamp(isoTimestamp: string | null | undefined): number {
  if (!isoTimestamp) return Number.NaN;
  return new Date(isoTimestamp).getTime();
}

/**
 * Milliseconds between `now` and an ISO timestamp, or NaN if it cannot be read.
 * Clamped at zero: a server clock a little ahead of the browser's should read
 * as "just now", never as a negative age.
 */
export function ageOf(isoTimestamp: string | null | undefined, now: number): number {
  const parsed = parseTimestamp(isoTimestamp);
  if (Number.isNaN(parsed)) return Number.NaN;
  return Math.max(0, now - parsed);
}

/**
 * Milliseconds from `now` until an ISO timestamp, or NaN if it cannot be read.
 * Deliberately *not* clamped — `relativeUntil` needs to see the negative to
 * call a deadline expired, which is exactly why this cannot just be `-ageOf`.
 */
export function timeUntil(isoTimestamp: string | null | undefined, now: number): number {
  const parsed = parseTimestamp(isoTimestamp);
  if (Number.isNaN(parsed)) return Number.NaN;
  return parsed - now;
}
