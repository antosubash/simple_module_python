import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import type React from 'react';
import { NavIcon } from '../components/NavIcon';
import type { MenuItem } from '../types';

interface AdminSectionLinkProps {
  /** The viewer's admin menu, already filtered by roles and permissions. */
  adminItems: MenuItem[];
  /** Sidebar `inactiveClass` from the host layout's theme. */
  className: string;
  onNavigate: () => void;
}

/**
 * The app shell's doorway into the admin section — the counterpart of
 * `AdminLayout`'s "Back to App".
 *
 * Every admin screen moved out of the main sidebar into `adminSidebar`, so
 * without this an admin signs in, lands on `/dashboard/`, and has no link to
 * Users, Settings, Branding or anything else they administer: the entries they
 * used before are simply gone from the shell.
 *
 * Renders nothing when the viewer has no admin entries. `adminSidebar` is
 * already filtered by roles *and* permissions, so a non-empty list is exactly
 * "this account has somewhere to go" — and `/admin` admits on that same
 * signal, so this never offers a link that would 403.
 */
export function AdminSectionLink({
  adminItems,
  className,
  onNavigate,
}: AdminSectionLinkProps): React.ReactElement | null {
  const { t } = useT();
  if (adminItems.length === 0) return null;

  return (
    <div className="pt-4 mt-4 border-t border-white/[0.06]">
      <Link
        href="/admin"
        onClick={onNavigate}
        className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium ${className}`}
      >
        <NavIcon name="shield" />
        {t(keys.ui.nav.admin)}
      </Link>
    </div>
  );
}
