import { describe, expect, it } from 'vitest';
import { ageOf, isStale, relativeAgeLabel, STALE_AFTER_MS } from './relative-time';

describe('relativeAgeLabel', () => {
  it('calls a very recent reading "just now"', () => {
    expect(relativeAgeLabel(0)).toBe('just now');
    expect(relativeAgeLabel(9_999)).toBe('just now');
  });

  it('counts seconds up to a minute', () => {
    expect(relativeAgeLabel(10_000)).toBe('10s ago');
    expect(relativeAgeLabel(59_000)).toBe('59s ago');
  });

  it('switches to minutes, then hours', () => {
    expect(relativeAgeLabel(60_000)).toBe('1m ago');
    expect(relativeAgeLabel(59 * 60_000)).toBe('59m ago');
    expect(relativeAgeLabel(60 * 60_000)).toBe('1h ago');
    expect(relativeAgeLabel(5 * 60 * 60_000)).toBe('5h ago');
  });

  it('never renders a negative age', () => {
    expect(relativeAgeLabel(-5_000)).toBe('just now');
  });

  it('degrades to "unknown" rather than NaN', () => {
    expect(relativeAgeLabel(Number.NaN)).toBe('unknown');
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
