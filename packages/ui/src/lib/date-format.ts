/**
 * The deck's date formats, in one place.
 *
 * Three screens write dates the same way — the audit table's `3 Sep 09:13:59`,
 * a task execution's timestamps, an account's `12 Mar 2026` — and each one had
 * grown its own `Intl` formatter. They also all hit the same trap: `en-GB`
 * gives the day-month order the deck draws, but ICU abbreviates September to
 * "Sept", which is four characters and knocks a mono column out of alignment.
 * So the month name comes from `en-US` (always three letters) and the order is
 * assembled here rather than delegated to a locale.
 *
 * These are deliberately not localised. They render machine evidence — audit
 * rows, execution stamps — in a fixed-width column where a reader compares
 * lines against each other, not prose.
 */

const MONTH_FORMAT = new Intl.DateTimeFormat('en-US', { month: 'short' });

const CLOCK_FORMAT = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

/** "Sep" — always three letters, unlike `en-GB`'s "Sept". */
export function shortMonth(date: Date): string {
  return MONTH_FORMAT.format(date);
}

/**
 * "3 Sep", or "03 Sep" when padded.
 *
 * The audit table's own cells are unpadded, the way the deck writes them; a
 * date *range* pads both ends so its two halves stay the same width.
 */
export function formatDayMonth(date: Date, { pad = false }: { pad?: boolean } = {}): string {
  const day = pad ? `${date.getDate()}`.padStart(2, '0') : `${date.getDate()}`;
  return `${day} ${shortMonth(date)}`;
}

/** "09:13:59" — 24-hour, zero-padded, in the reader's own timezone. */
export function formatClock(date: Date): string {
  return CLOCK_FORMAT.format(date);
}

/**
 * "3 Sep 09:13:59" from an ISO timestamp.
 *
 * An unparseable value is returned as it arrived: it is still evidence, and
 * showing it raw beats showing "Invalid Date" where a reader expects a time.
 */
export function formatDayMonthTime(timestamp: string): string {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return timestamp;
  return `${formatDayMonth(parsed)} ${formatClock(parsed)}`;
}

/**
 * "12 Mar 2026" — a date, not a timestamp.
 *
 * For facts whose minute never matters: when an account was created, when an
 * invite expires.
 */
export function formatDayMonthYear(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return fallback;
  return `${formatDayMonth(parsed)} ${parsed.getFullYear()}`;
}
