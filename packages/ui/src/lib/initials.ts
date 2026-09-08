/**
 * Two letters to stand in for a person when there is no avatar image.
 *
 * Every list of users in the app shows a face; most accounts never upload one.
 * The fallback has to work from whatever the record actually has — a full
 * name, a username, or only an email — and still produce something stable and
 * recognisable rather than a blank circle.
 */
export function initials(name?: string | null, email?: string | null): string {
  const words = (name ?? '').trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) {
    return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  }
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();

  // No name: the local part of the email is the closest thing to one.
  const local = (email ?? '').trim().split('@')[0];
  if (local) return local.slice(0, 2).toUpperCase();

  return '?';
}
