import { Link } from '@inertiajs/react';
import type React from 'react';
import { SidebarLayout } from './SidebarLayout';

const THEME = {
  sidebarBg: 'bg-admin-bg',
  accentColor: 'bg-gradient-to-br from-red-500 to-red-700',
  avatarBg: 'bg-red-700',
  hoverBg: 'hover:bg-admin-hover',
  activeClass: 'bg-red-600/15 text-red-300 border-l-2 border-red-400',
  inactiveClass:
    'text-admin-text hover:bg-admin-hover hover:text-white border-l-2 border-transparent',
  mutedTextClass: 'text-admin-text-muted',
  mobileTitleLabel: 'Admin',
} as const;

const adminBadge = (
  <div className="px-3 pt-4 pb-2">
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-red-500/10 border border-red-500/20">
      <svg
        aria-hidden="true"
        className="w-4 h-4 text-red-400"
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
      <span className="text-xs font-semibold text-red-400 uppercase tracking-wider">
        Admin Panel
      </span>
    </div>
  </div>
);

const backToApp = (
  <div className="pt-4 mt-4 border-t border-white/[0.06]">
    <Link
      href="/dashboard"
      className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-admin-text-subtle hover:bg-admin-hover hover:text-white transition-colors"
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
      Back to App
    </Link>
  </div>
);

export function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarLayout
      menuKey="adminSidebar"
      theme={THEME}
      headerSlot={adminBadge}
      footerNavSlot={backToApp}
    >
      {children}
    </SidebarLayout>
  );
}
