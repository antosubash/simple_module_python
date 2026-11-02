import { describe, expect, test } from 'vitest';
import {
  formatChangePair,
  formatChangeValue,
  formatDateRange,
  formatEntryTime,
  parseIsoDate,
  toIsoDate,
} from '../audit_log/pages/components/format';

describe('formatEntryTime', () => {
  test('renders the deck format: d MMM HH:mm:ss', () => {
    // Built in local time so the assertion holds in any timezone — the column
    // shows the reader's clock, not UTC.
    const stamp = new Date(2026, 7, 19, 14, 2, 11).toISOString();

    expect(formatEntryTime(stamp)).toBe('19 Aug 14:02:11');
  });

  test('uses a 24-hour clock with padded hours', () => {
    expect(formatEntryTime(new Date(2026, 7, 19, 9, 3, 40).toISOString())).toBe('19 Aug 09:03:40');
  });

  test('the day is not padded — `d MMM`, not `dd MMM`', () => {
    expect(formatEntryTime(new Date(2026, 7, 5, 14, 2, 11).toISOString())).toBe('5 Aug 14:02:11');
  });

  test('midnight is 00, never 24', () => {
    expect(formatEntryTime(new Date(2026, 7, 19, 0, 0, 0).toISOString())).toBe('19 Aug 00:00:00');
  });

  test('an unparseable timestamp is shown as sent rather than as Invalid Date', () => {
    expect(formatEntryTime('not a time')).toBe('not a time');
  });
});

describe('date-only values', () => {
  test('parses as local midnight, not UTC', () => {
    // `new Date('2026-08-19')` is UTC midnight and renders as the 18th for
    // every reader west of Greenwich.
    const parsed = parseIsoDate('2026-08-19');

    expect(parsed?.getFullYear()).toBe(2026);
    expect(parsed?.getMonth()).toBe(7);
    expect(parsed?.getDate()).toBe(19);
  });

  test('round-trips through toIsoDate', () => {
    expect(toIsoDate(new Date(2026, 7, 1))).toBe('2026-08-01');
  });

  test('rejects anything that is not a plain date', () => {
    expect(parseIsoDate('2026-08-19T10:00')).toBeNull();
    expect(parseIsoDate('')).toBeNull();
  });
});

describe('formatDateRange', () => {
  test('reads as the deck writes it — padded ends, unlike the time cell', () => {
    expect(formatDateRange('2026-08-01', '2026-08-19')).toBe('01 Aug – 19 Aug');
  });

  test('an open end still shows the end that was chosen', () => {
    expect(formatDateRange('2026-08-01', null)).toBe('01 Aug –');
    expect(formatDateRange(null, '2026-08-19')).toBe('– 19 Aug');
  });

  test('no range at all is empty, so the field can show its placeholder', () => {
    expect(formatDateRange(null, null)).toBe('');
  });
});

describe('formatChangeValue', () => {
  test('keeps null and the empty string apart', () => {
    expect(formatChangeValue(null)).toBe('null');
    expect(formatChangeValue('')).toBe('""');
  });

  test('a missing key reads as null', () => {
    expect(formatChangeValue(undefined)).toBe('null');
  });

  test('booleans and numbers render bare', () => {
    expect(formatChangeValue(true)).toBe('true');
    expect(formatChangeValue(12)).toBe('12');
  });

  test('pairs are spaced around the arrow', () => {
    expect(formatChangePair(true, false)).toBe('true → false');
  });
});

describe('timestamp values inside a change', () => {
  test('an ISO datetime is shortened to the Time column\u2019s own format', () => {
    // Rendered whole, one of these is 32 characters and pushes the Changes
    // column past the card it sits in.
    const stamp = new Date(2026, 8, 3, 9, 13, 59).toISOString();

    expect(formatChangeValue(stamp)).toBe('3 Sep 09:13:59');
  });

  test('both sides serialise alike however precise the server was', () => {
    // The old side is second-precision, the new side carries microseconds and
    // an offset. Whole, the reader compares 32 characters to spot one second.
    expect(formatChangePair('2026-09-03T09:13:59', '2026-09-03T09:14:00.123456')).toBe(
      '3 Sep 09:13:59 → 3 Sep 09:14:00',
    );
  });

  test('a date-only string is left alone — it is not a timestamp', () => {
    expect(formatChangeValue('2026-09-03')).toBe('"2026-09-03"');
  });

  test('a string that merely contains a date is left alone', () => {
    expect(formatChangeValue('backup 2026-09-03T09:13:59 done')).toBe(
      '"backup 2026-09-03T09:13:59 done"',
    );
  });
});
