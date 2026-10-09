import { usePage } from '@inertiajs/react';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import type { SharedProps } from '@simple-module-py/ui/types';
import { createContext, type ReactNode, useContext } from 'react';

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
  const props = page.props as unknown as Partial<SharedProps>;
  const inShell =
    isAdminPath(page.url) &&
    Boolean(props.auth?.isAuthenticated) &&
    Array.isArray(props.menus?.adminSidebar) &&
    props.menus.adminSidebar.length > 0;
  if (!inShell) return <>{children}</>;
  return (
    <InShell.Provider value>
      <AdminLayout>{children}</AdminLayout>
    </InShell.Provider>
  );
}
