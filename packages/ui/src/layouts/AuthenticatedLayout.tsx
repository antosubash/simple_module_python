import type React from 'react';
import { SidebarLayout } from './SidebarLayout';

const THEME = {
  sidebarBg: 'bg-sidebar',
  accentColor: 'bg-primary-500',
  avatarBg: 'bg-primary-700',
  hoverBg: 'hover:bg-sidebar-hover',
  activeClass: 'bg-primary-600/20 text-white',
  inactiveClass: 'text-sidebar-text hover:bg-sidebar-hover hover:text-white',
  mutedTextClass: 'text-sidebar-text-muted',
  mobileTitleLabel: 'SimpleModule',
} as const;

export function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarLayout menuKey="sidebar" theme={THEME}>
      {children}
    </SidebarLayout>
  );
}
