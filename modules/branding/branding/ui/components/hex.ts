const HEX = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i;

/**
 * Normalise what an admin typed into `#rrggbb`, or `null` when it is not a
 * 3- or 6-digit hex colour. The leading `#` is optional; case is folded.
 * The server only accepts `#rrggbb`, so 3-digit shorthand is expanded here.
 */
export function normalizeHex(raw: string): string | null {
  const match = HEX.exec(raw.trim());
  if (!match) return null;
  let digits = match[1].toLowerCase();
  if (digits.length === 3) digits = [...digits].map((d) => d + d).join('');
  return `#${digits}`;
}

/** Empty means "use the theme default", which is a valid stored value. */
export function isValidColor(raw: string): boolean {
  return raw.trim() === '' || normalizeHex(raw) !== null;
}
