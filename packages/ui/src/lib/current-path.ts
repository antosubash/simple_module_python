/**
 * The path part of Inertia's page url.
 *
 * `usePage().url` is an absolute url — `http://host:8300/users/admin/add` —
 * while every menu entry is a root-relative path. Comparing the two directly
 * with `startsWith` is always false, which is why the sidebar's active-item
 * styling never rendered on any page: the design existed, the condition
 * selecting it could not fire.
 *
 * Query and hash are dropped too, so `/files?q=logo` still resolves to the
 * Files section.
 */
export function toPath(url: string): string {
  try {
    // The base only matters for relative inputs; the pathname is what we keep.
    return new URL(url, 'http://relative.invalid').pathname;
  } catch {
    return url;
  }
}

/** Path with any trailing slashes removed, so `/files/` and `/files` compare equal. */
function trimmed(url: string): string {
  return toPath(url).replace(/\/+$/, '');
}

/**
 * Whether two urls name the same page.
 *
 * Menu urls in this app are not consistent about trailing slashes
 * (`/users/admin` but `/file-storage/`), so an exact string compare makes
 * matching depend on which spelling a caller happened to use.
 */
export function samePath(a: string, b: string): boolean {
  return trimmed(a) === trimmed(b);
}

/**
 * Whether `url` is inside `sectionUrl`.
 *
 * Compared segment-wise: `/users` must not claim `/users-archive`, but must
 * still claim `/users/admin`. Trailing slashes on either side are irrelevant.
 */
export function isUnder(url: string, sectionUrl: string): boolean {
  const path = trimmed(url);
  const section = trimmed(sectionUrl);
  if (section === '') return path === '';
  return path === section || path.startsWith(`${section}/`);
}
