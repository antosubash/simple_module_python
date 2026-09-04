import { describe, expect, test } from 'vitest';

import {
  formatClock,
  formatDayMonth,
  formatDayMonthTime,
  formatDayMonthYear,
  shortMonth,
} from './date-format';

describe('shortMonth', () => {
  test('abbreviates September to three letters', () => {
    // `en-GB` says "Sept", which is a fourth character in a mono column that
    // the deck aligns on three.
    expect(shortMonth(new Date(2026, 8, 3))).toBe('Sep');
  });

  test('every month is three letters', () => {
    const lengths = Array.from({ length: 12 }, (_, m) => shortMonth(new Date(2026, m, 1)).length);
    expect(new Set(lengths)).toEqual(new Set([3]));
  });
});

describe('formatDayMonth', () => {
  test('is unpadded by default — `d MMM`, not `dd MMM`', () => {
    expect(formatDayMonth(new Date(2026, 7, 5))).toBe('5 Aug');
  });

  test('pads on request, so the two ends of a range are the same width', () => {
    expect(formatDayMonth(new Date(2026, 7, 5), { pad: true })).toBe('05 Aug');
  });
});

describe('formatClock', () => {
  test('is 24-hour and zero-padded', () => {
    expect(formatClock(new Date(2026, 7, 19, 9, 3, 40))).toBe('09:03:40');
  });

  test('midnight is 00, never 24', () => {
    expect(formatClock(new Date(2026, 7, 19, 0, 0, 0))).toBe('00:00:00');
  });
});

describe('formatDayMonthTime', () => {
  test('renders the deck format', () => {
    // Built in local time so the assertion holds in any timezone — the column
    // shows the reader's clock, not UTC.
    expect(formatDayMonthTime(new Date(2026, 8, 3, 9, 13, 59).toISOString())).toBe(
      '3 Sep 09:13:59',
    );
  });

  test('an unparseable timestamp is shown as sent', () => {
    expect(formatDayMonthTime('not a time')).toBe('not a time');
  });
});

describe('formatDayMonthYear', () => {
  test('reads day-first, as the deck writes it', () => {
    expect(formatDayMonthYear(new Date(2026, 2, 12).toISOString(), '—')).toBe('12 Mar 2026');
  });

  test('falls back for a missing or unparseable value', () => {
    expect(formatDayMonthYear(null, '—')).toBe('—');
    expect(formatDayMonthYear('not a date', '—')).toBe('—');
  });
});
