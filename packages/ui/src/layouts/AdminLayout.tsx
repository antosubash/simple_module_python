import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import type React from 'react';
import { SidebarLayout } from './SidebarLayout';

// Same visual language as the app sidebar — the admin area announces itself
// through the panel badge and its own menu, not through an alarm color.
const THEME = {
  sidebarBg: 'bg-app-sidebar',
  accentColor: 'bg-gradient-to-br from-primary-400 to-primary-600',
  avatarBg: 'bg-primary-700',
  hoverBg: 'hover:bg-app-sidebar-hover',
  activeClass: 'bg-primary-600/15 text-primary-300 border-l-2 border-primary-400',
  inactiveClass:
    'text-app-sidebar-text hover:bg-app-sidebar-hover hover:text-white border-l-2 border-transparent',
  mutedTextClass: 'text-app-sidebar-text-muted',
  mobileTitleLabel: 'Admin',
} as const;

// A link, not a label: the section root is the one admin destination with no
// sidebar entry of its own, and the badge is where a user looks for "home"
// within a section. A component rather than a constant so the label can go
// through the catalog — `t()` cannot be called at module scope.
function AdminBadge() {
  const { t } = useT();
  return (
    <div className="px-3 pt-4 pb-2">
      <Link
        href="/admin"
        className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-primary-500/10 border border-primary-500/20 transition-colors hover:bg-primary-500/20"
      >
        <svg
          aria-hidden="true"
          className="w-4 h-4 text-primary-400"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"
          />
        </svg>
        <span className="text-xs font-semibold text-primary-400 uppercase tracking-wider">
          {t(keys.ui.admin.panel_badge)}
        </span>
      </Link>
    </div>
  );
}

function BackToApp() {
  const { t } = useT();
  return (
    <div className="pt-4 mt-4 border-t border-white/[0.06]">
      <Link
        href="/dashboard/"
        className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-app-sidebar-text-muted hover:bg-app-sidebar-hover hover:text-white transition-colors"
      >
        <svg
          aria-hidden="true"
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3"
          />
        </svg>
        {t(keys.ui.admin.back_to_app)}
      </Link>
    </div>
  );
}

export function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarLayout
      menuKey="adminSidebar"
      theme={THEME}
      headerSlot={<AdminBadge />}
      footerNavSlot={<BackToApp />}
    >
      {children}
    </SidebarLayout>
  );
}
