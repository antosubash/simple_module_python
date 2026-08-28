const SIMPLE_EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Split a pasted block on commas, semicolons, and any whitespace. */
export function parseInviteEmails(value: string): string[] {
  return value
    .split(/[\s,;]+/)
    .map((email) => email.trim())
    .filter(Boolean);
}

/**
 * Catch obvious typos before submit while leaving authoritative validation to
 * the backend's EmailStr validator.
 */
export function isPlausibleEmail(value: string): boolean {
  return SIMPLE_EMAIL_PATTERN.test(value);
}
