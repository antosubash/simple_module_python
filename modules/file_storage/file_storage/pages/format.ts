/** Byte counts as the deck writes them: "18 KB", "840 KB", "1.2 GB". */
export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${round(n / 1024)} KB`;
  if (n < 1024 * 1024 * 1024) return `${round(n / 1024 / 1024)} MB`;
  return `${round(n / 1024 / 1024 / 1024)} GB`;
}

// One decimal, but never a trailing ".0": a 25 MB limit reads as "25 MB", and
// only a value that genuinely needs the precision spends a character on it.
function round(value: number): number {
  return Number.parseFloat(value.toFixed(1));
}

/**
 * The allow-list as a human would say it: "pdf, png, csv, sql".
 *
 * MIME subtypes carry the information; the family prefix is noise once four of
 * them are listed side by side.
 */
export function describeTypes(contentTypes: string[]): string {
  const seen = new Set<string>();
  for (const type of contentTypes) {
    const subtype = type.split('/').at(-1);
    if (subtype) seen.add(subtype);
  }
  return [...seen].join(', ');
}
