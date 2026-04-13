import { usePage } from '@inertiajs/react';

/**
 * Returns a `can(permission)` function that checks if the current user
 * has a specific permission. Wildcard expansion happens server-side,
 * so this is a simple array inclusion check.
 */
export function usePermissions() {
  const page = usePage<{ props: { auth?: { permissions?: string[] } } }>();
  const permissions: string[] =
    (page.props as { auth?: { permissions?: string[] } })?.auth?.permissions ?? [];

  function can(permission: string): boolean {
    return permissions.includes(permission);
  }

  return { can, permissions };
}
