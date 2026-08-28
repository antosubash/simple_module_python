import { describe, expect, it } from 'vitest';
import { ageOf, isStale, RELATIVE_AGE_KEYS, relativeAge, STALE_AFTER_MS } from './relative-time';

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
