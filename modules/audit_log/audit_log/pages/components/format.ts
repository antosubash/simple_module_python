/**
 * Formatting shared by the audit table, its filters and its empty state.
 *
 * Kept out of the components because every one of these is a rule with an
 * edge that a test should be able to reach without rendering a table: what a
 * cleared field looks like next to a nulled one, what a date-only range reads
 * as, and what happens to a timestamp the server sent in a shape nobody
 * expected.
 */

/**
 * "19 Aug 14:02:11" — the deck's `d MMM HH:mm:ss`.
 *
 * Fixed to en-GB rather than the reader's locale: the column is 150px of
 * tabular evidence, and en-US would widen every row with "PM" and reorder the
 * date away from the range control sitting above it. Built from two
 * formatters because a single one interposes a comma between them.
 */
const DAY_FORMAT = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short' });
const CLOCK_FORMAT = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

export function formatEntryTime(timestamp: string): string {
  const parsed = new Date(timestamp);
  // An unparseable timestamp is still evidence; showing it raw beats showing
  // "Invalid Date" where a reader expects a time.
  if (Number.isNaN(parsed.getTime())) return timestamp;
  return `${DAY_FORMAT.format(parsed)} ${CLOCK_FORMAT.format(parsed)}`;
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
  const start = from ? parseIsoDate(from) : null;
  const end = to ? parseIsoDate(to) : null;
  if (start && end) return `${DAY_FORMAT.format(start)} – ${DAY_FORMAT.format(end)}`;
  if (start) return `${DAY_FORMAT.format(start)} –`;
  if (end) return `– ${DAY_FORMAT.format(end)}`;
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
  return JSON.stringify(value) ?? 'null';
}

/** `true → false`, spaced as the deck spaces it. */
export function formatChangePair(oldValue: unknown, newValue: unknown): string {
  return `${formatChangeValue(oldValue)} → ${formatChangeValue(newValue)}`;
}
