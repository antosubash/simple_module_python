import { describe, expect, it } from 'vitest';
import {
  ageOf,
  isStale,
  RELATIVE_AGE_KEYS,
  RELATIVE_UNTIL_KEYS,
  relativeAge,
  relativeUntil,
  STALE_AFTER_MS,
  timeUntil,
} from './relative-time';

// The wording lives in the ui catalog, so the unit under test here is which
// bucket an age falls into and what count it reports — not the English.
describe('relativeAge', () => {
  it('calls a very recent reading "just now"', () => {
    expect(relativeAge(0)).toEqual({ key: RELATIVE_AGE_KEYS.justNow });
    expect(relativeAge(9_999)).toEqual({ key: RELATIVE_AGE_KEYS.justNow });
  });

  it('counts seconds up to a minute', () => {
    expect(relativeAge(10_000)).toEqual({ key: RELATIVE_AGE_KEYS.seconds, count: 10 });
    expect(relativeAge(59_000)).toEqual({ key: RELATIVE_AGE_KEYS.seconds, count: 59 });
  });

  it('switches to minutes, then hours', () => {
    expect(relativeAge(60_000)).toEqual({ key: RELATIVE_AGE_KEYS.minutes, count: 1 });
    expect(relativeAge(59 * 60_000)).toEqual({ key: RELATIVE_AGE_KEYS.minutes, count: 59 });
    expect(relativeAge(60 * 60_000)).toEqual({ key: RELATIVE_AGE_KEYS.hours, count: 1 });
    expect(relativeAge(5 * 60 * 60_000)).toEqual({ key: RELATIVE_AGE_KEYS.hours, count: 5 });
  });

  it('never renders a negative age', () => {
    expect(relativeAge(-5_000)).toEqual({ key: RELATIVE_AGE_KEYS.justNow });
  });

  it('degrades to "unknown" rather than NaN', () => {
    expect(relativeAge(Number.NaN)).toEqual({ key: RELATIVE_AGE_KEYS.unknown });
  });
});

describe('isStale', () => {
  it('is false below the threshold and true at or above it', () => {
    expect(isStale(STALE_AFTER_MS - 1)).toBe(false);
    expect(isStale(STALE_AFTER_MS)).toBe(true);
  });

  it('treats an unreadable age as not stale, so nothing is falsely flagged', () => {
    expect(isStale(Number.NaN)).toBe(false);
  });
});

describe('ageOf', () => {
  const now = Date.parse('2026-08-19T12:00:00Z');

  it('measures back from now', () => {
    expect(ageOf('2026-08-19T11:59:30Z', now)).toBe(30_000);
  });

  it('clamps a server clock running ahead to zero', () => {
    expect(ageOf('2026-08-19T12:00:30Z', now)).toBe(0);
  });

  it('returns NaN for a missing or unparseable timestamp', () => {
    expect(ageOf(null, now)).toBeNaN();
    expect(ageOf('not a date', now)).toBeNaN();
  });
});

describe('timeUntil', () => {
  const now = Date.parse('2026-08-19T12:00:00Z');

  it('counts forward to a deadline', () => {
    expect(timeUntil('2026-08-19T12:00:30Z', now)).toBe(30_000);
  });

  it('goes negative once the deadline has passed, so it can read as expired', () => {
    // The mirror of `ageOf`'s clamp, and the reason the two cannot be the same
    // function: clamping here would make every past expiry read as "in 0m".
    expect(timeUntil('2026-08-19T11:59:30Z', now)).toBe(-30_000);
    expect(relativeUntil(timeUntil('2026-08-19T11:59:30Z', now))).toEqual({
      key: RELATIVE_UNTIL_KEYS.expired,
    });
  });

  it('returns NaN for a missing or unparseable timestamp, exactly as ageOf does', () => {
    expect(timeUntil(null, now)).toBeNaN();
    expect(timeUntil(undefined, now)).toBeNaN();
    expect(timeUntil('not a date', now)).toBeNaN();
  });
});

describe('relativeAge over longer spans', () => {
  const DAY = 24 * 60 * 60_000;

  it('counts days once an age passes a day', () => {
    expect(relativeAge(DAY)).toEqual({ key: RELATIVE_AGE_KEYS.days, count: 1 });
    expect(relativeAge(29 * DAY)).toEqual({ key: RELATIVE_AGE_KEYS.days, count: 29 });
  });

  it('switches to months at thirty days', () => {
    expect(relativeAge(30 * DAY)).toEqual({ key: RELATIVE_AGE_KEYS.months, count: 1 });
    expect(relativeAge(364 * DAY)).toEqual({ key: RELATIVE_AGE_KEYS.months, count: 12 });
  });

  it('switches to years at a year', () => {
    expect(relativeAge(365 * DAY)).toEqual({ key: RELATIVE_AGE_KEYS.years, count: 1 });
    expect(relativeAge(800 * DAY)).toEqual({ key: RELATIVE_AGE_KEYS.years, count: 2 });
  });
});

describe('relativeUntil', () => {
  const MINUTE = 60_000;
  const HOUR = 60 * MINUTE;
  const DAY = 24 * HOUR;

  it('reports anything already past as expired', () => {
    expect(relativeUntil(0)).toEqual({ key: RELATIVE_UNTIL_KEYS.expired });
    expect(relativeUntil(-1)).toEqual({ key: RELATIVE_UNTIL_KEYS.expired });
  });

  it('counts minutes below the hour, never rounding down to zero', () => {
    expect(relativeUntil(30_000)).toEqual({ key: RELATIVE_UNTIL_KEYS.minutes, count: 1 });
    expect(relativeUntil(59 * MINUTE)).toEqual({ key: RELATIVE_UNTIL_KEYS.minutes, count: 59 });
  });

  it('counts hours below a day, then days', () => {
    expect(relativeUntil(HOUR)).toEqual({ key: RELATIVE_UNTIL_KEYS.hours, count: 1 });
    expect(relativeUntil(23 * HOUR)).toEqual({ key: RELATIVE_UNTIL_KEYS.hours, count: 23 });
    expect(relativeUntil(DAY)).toEqual({ key: RELATIVE_UNTIL_KEYS.days, count: 1 });
    expect(relativeUntil(10 * DAY)).toEqual({ key: RELATIVE_UNTIL_KEYS.days, count: 10 });
  });

  it('degrades to "unknown" rather than NaN', () => {
    expect(relativeUntil(Number.NaN)).toEqual({ key: RELATIVE_AGE_KEYS.unknown });
  });
});
