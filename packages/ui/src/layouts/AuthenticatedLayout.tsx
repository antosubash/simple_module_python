import { Toaster } from '@simple-module-py/ui/components/ui/sonner';
import type React from 'react';
import { DEFAULT_SIDEBAR_THEME, SidebarLayout } from './SidebarLayout';

const THEME = {
  ...DEFAULT_SIDEBAR_THEME,
  mobileTitleLabel: 'SimpleModule',
} as const;

export function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    // Locale lives in the topbar beside search (and in the drawer footer on
    // phones) — the sidebar header slot put a language control directly under
    // the wordmark, where it read as part of the branding rather than a setting.
    <SidebarLayout menuKey="sidebar" theme={THEME}>
      {children}
      <Toaster richColors position="top-right" />
    </SidebarLayout>
  );
}
