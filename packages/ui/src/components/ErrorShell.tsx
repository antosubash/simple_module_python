import { usePage } from '@inertiajs/react';
import { createContext, type ReactNode, useContext } from 'react';
import { AdminLayout } from '../layouts/AdminLayout';
import { AuthenticatedLayout } from '../layouts/AuthenticatedLayout';
import type { SharedProps } from '../types';

/** `/admin` or anything under `/admin/` — not `/administer`. */
export function isAdminPath(url: string): boolean {
  const path = url.split(/[?#]/, 1)[0];
  return path === '/admin' || path.startsWith('/admin/');
}

const InShell = createContext(false);
export const useInAdminShell = () => useContext(InShell);

/**
 * Keeps an admin inside the admin shell when a page under /admin fails (#422).
 * Only for a signed-in viewer whose admin menu reached the page: an anonymous
 * 401/419 has no admin to keep in context, and a 500 raised before the shared
 * props were built has no menu to render.
 */
export function ErrorShell({ children }: { children: ReactNode }) {
  const page = usePage();
  const props = page.props as Partial<SharedProps>;
  const inShell =
    isAdminPath(page.url) &&
    Boolean(props.auth?.isAuthenticated) &&
    Array.isArray(props.menus?.adminSidebar) &&
    props.menus.adminSidebar.length > 0;
  // Outside /admin, a signed-in viewer's error page (404, 403, 5xx alike) keeps
  // the app layout too (#575), consistent with the admin shell. Needs a menu:
  // without shared props there is nothing to render, and an anonymous visitor
  // has no app to stay in.
  const inAppShell =
    !isAdminPath(page.url) &&
    Boolean(props.auth?.isAuthenticated) &&
    (props.menus?.sidebar?.length ?? 0) + (props.menus?.adminSidebar?.length ?? 0) > 0;
  if (inAppShell) {
    return (
      <InShell.Provider value>
        <AuthenticatedLayout>{children}</AuthenticatedLayout>
      </InShell.Provider>
    );
  }
  if (!inShell) return <>{children}</>;
  return (
    <InShell.Provider value>
      <AdminLayout>{children}</AdminLayout>
    </InShell.Provider>
  );
}
