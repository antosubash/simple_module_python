/**
 * Inertia v3 `serverHead` resolver for the `_head` prop that a view's
 * `inertia.render(..., head=Head(...))` sends (#535).
 *
 * Returning the tags lets Inertia's head manager re-emit them on every client
 * visit, replacing the server-rendered ones by their `data-inertia` key rather
 * than duplicating them, and drop them when the next page sends none.
 */
export const SERVER_HEAD_PROP = '_head';

export function resolveServerHead(page: { props?: Record<string, unknown> }): string[] {
  const tags = page.props?.[SERVER_HEAD_PROP];
  return Array.isArray(tags) ? tags.filter((t): t is string => typeof t === 'string') : [];
}
