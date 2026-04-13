import { Toaster } from '@ui/components/ui/sonner';
import type React from 'react';
import { SidebarLayout } from './SidebarLayout';

const THEME = {
  sidebarBg: 'bg-app-sidebar',
  accentColor: 'bg-gradient-to-br from-primary-400 to-primary-600',
  avatarBg: 'bg-primary-700',
  hoverBg: 'hover:bg-app-sidebar-hover',
  activeClass: 'bg-primary-600/15 text-primary-300 border-l-2 border-primary-400',
  inactiveClass:
    'text-app-sidebar-text hover:bg-app-sidebar-hover hover:text-white border-l-2 border-transparent',
  mutedTextClass: 'text-app-sidebar-text-muted',
  mobileTitleLabel: 'SimpleModule',
} as const;

export function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarLayout menuKey="sidebar" theme={THEME}>
      {children}
      <Toaster richColors position="top-right" />
    </SidebarLayout>
  );
}
