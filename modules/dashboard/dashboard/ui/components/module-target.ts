import { isUnder, samePath, trimmed } from '@simple-module-py/ui/lib/current-path';
import type { MenuItem, SharedProps } from '@simple-module-py/ui/types';

interface ModuleMount {
  /** The module's own view prefix, or '' when it ships no views. */
  url: string;
  /** Second mount point for a partly-administrative module, or ''. */
  admin_url: string;
}

/**
 * Resolve each module tile's link target against the viewer's own menus.
 *
 * The server cannot filter these links per user — the stats payload is
 * process-wide cached for 30s — so reachability is decided here against the
 * menus the middleware already filtered for this session. POST entries
 * (Logout) are excluded: the tile renders a GET link, so adopting one as a
 * module's target hands the user a 405.
 */
export function moduleTargetResolver(
  menus: SharedProps['menus'] | undefined,
  modules: ModuleMount[],
): (url: string, adminUrl: string) => string {
  const menuUrls = [
    ...(menus?.sidebar ?? []),
    ...(menus?.adminSidebar ?? []),
    ...(menus?.navbar ?? []),
    ...(menus?.userDropdown ?? []),
  ]
    .filter((item: MenuItem) => (item.method ?? 'get') === 'get')
    .map((item: MenuItem) => item.url);

  // Every module's own prefix, so the fallback below can tell "this entry is
  // mine" from "this entry belongs to a module mounted deeper than me".
  const modulePrefixes = modules
    .flatMap((m) => [m.url, m.admin_url])
    .map((url) => trimmed(url))
    .filter(Boolean);

  function exactMenu(url: string): string {
    const prefix = trimmed(url);
    if (!prefix) return '';
    return menuUrls.find((menuUrl) => samePath(menuUrl, prefix)) ?? '';
  }

  function menuUnderPrefix(url: string): string {
    const prefix = trimmed(url);
    if (!prefix) return '';
    return (
      menuUrls.find(
        (menuUrl) =>
          isUnder(menuUrl, prefix) &&
          !modulePrefixes.some((other) => other.length > prefix.length && isUnder(menuUrl, other)),
      ) ?? ''
    );
  }

  /**
   * Matching the view prefix exactly is not enough: a module often mounts its
   * landing screen below its own prefix (background_tasks is
   * `/admin/background-tasks`, its menu entry is `/admin/background-tasks/`),
   * and an exact match leaves those tiles permanently inert for admins who can
   * in fact open them. So fall back to the first menu entry that lives under
   * the prefix — but only if no *other* module owns a longer prefix of that
   * entry, or a module mounted at `/admin` would adopt the background-tasks
   * entry and link its tile to somebody else's screen.
   *
   * A module that is only partly administrative mounts its admin screens
   * outside its own `view_prefix` (Users serves sign-in at `/users` and
   * management at `/admin/users`), so both prefixes are searched.
   *
   * Every exact match is tried before any under-prefix guess, rather than
   * exhausting one prefix before the other. Searching the admin prefix first
   * outright sent the Dashboard tile to Doctor: dashboard owns both
   * `/dashboard` and `/admin/doctor`, and its own screen is the one the tile
   * is for. An exact hit is unambiguous evidence of "this is the module's
   * landing screen", so it beats a guess on either prefix — which also keeps
   * the Users tile on `/admin/users` rather than falling through to
   * `/users/me` and opening the viewer's own profile.
   */
  return function moduleTarget(url: string, adminUrl: string): string {
    for (const candidate of [url, adminUrl]) {
      const hit = candidate ? exactMenu(candidate) : '';
      if (hit) return hit;
    }
    for (const candidate of [adminUrl, url]) {
      const hit = candidate ? menuUnderPrefix(candidate) : '';
      if (hit) return hit;
    }
    return '';
  };
}
