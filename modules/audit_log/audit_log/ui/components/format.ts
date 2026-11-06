/**
 * Formatting shared by the audit table, its filters and its empty state.
 *
 * Kept out of the components because every one of these is a rule with an
 * edge that a test should be able to reach without rendering a table: what a
 * cleared field looks like next to a nulled one, what a date-only range reads
 * as, and what happens to a timestamp the server sent in a shape nobody
 * expected.
 */

import { formatDayMonth, formatDayMonthTime } from '@simple-module-py/ui/lib/date-format';

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * An ISO timestamp as the server writes them, with or without sub-seconds and
 * offset: `2026-09-03T09:13:59`, `…59.123456`, `…59.123456+00:00`, `…59Z`.
 */
const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/;

/**
 * "19 Aug 14:02:11" — the deck's `d MMM HH:mm:ss`.
 *
 * Fixed rather than locale-dependent: the column is 150px of tabular evidence,
 * and en-US would widen every row with "PM" and reorder the date away from the
 * range control sitting above it. The month is `en-US`'s three-letter form
 * because `en-GB` abbreviates September to "Sept", which is a fourth character
 * in a column the deck aligns on three. See `ui/lib/date-format`.
 *
 * `d`, not `dd`: the cell's day is unpadded ("5 Aug"). The range field below
 * pads its ends ("01 Aug – 19 Aug") because the deck draws them that way — two
 * digits keep the two halves of a range the same width.
 */
export function formatEntryTime(timestamp: string): string {
  return formatDayMonthTime(timestamp);
}

/**
 * Parse a date-only value as *local* midnight.
 *
 * `new Date('2026-08-19')` is UTC midnight, which renders as 18 Aug for every
 * reader west of Greenwich — so the day someone picked in the calendar comes
 * back as the day before.
 */
export function parseIsoDate(value: string): Date | null {
  const match = ISO_DATE.exec(value);
  if (!match) return null;
  const parsed = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/** The inverse of {@link parseIsoDate}: a local date as `yyyy-mm-dd`. */
export function toIsoDate(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/** "01 Aug – 19 Aug", or one end of it, or an empty string for no range. */
export function formatDateRange(from: string | null, to: string | null): string {
  const pad = { pad: true };
  const start = from ? parseIsoDate(from) : null;
  const end = to ? parseIsoDate(to) : null;
  if (start && end) return `${formatDayMonth(start, pad)} – ${formatDayMonth(end, pad)}`;
  if (start) return `${formatDayMonth(start, pad)} –`;
  if (end) return `– ${formatDayMonth(end, pad)}`;
  return '';
}

/**
 * One side of a change.
 *
 * `JSON.stringify` rather than `String()` so a field cleared to `""` and a
 * field set to NULL stay visibly different — they are different events, and
 * rendering both as nothing at all was the previous behaviour.
 */
export function formatChangeValue(value: unknown): string {
  if (value === undefined) return 'null';
  // A stored timestamp arrives as an ISO string, and the two sides of one
  // change rarely agree on how much of it: `…:59` against
  // `…:59.123456+00:00`. Rendered whole they force the Changes column wider
  // than the card, and the reader compares 32 characters to spot a
  // one-second difference. Shortened to the same `d MMM HH:mm:ss` the Time
  // column uses, both sides serialise alike and the diff is the difference.
  if (typeof value === 'string' && ISO_DATETIME.test(value)) {
    return formatDayMonthTime(value);
  }
  return JSON.stringify(value) ?? 'null';
}

/** `true → false`, spaced as the deck spaces it. */
export function formatChangePair(oldValue: unknown, newValue: unknown): string {
  return `${formatChangeValue(oldValue)} → ${formatChangeValue(newValue)}`;
}
