/**
 * The sidebar's visual language, shared by every sidebar-driven layout.
 *
 * Split from SidebarLayout so the palette is a data concern with one home:
 * AdminLayout and AuthenticatedLayout both spread the default and override
 * only `mobileTitleLabel`, so a tweak lands once instead of drifting between
 * the two shells.
 */

export interface SidebarTheme {
  sidebarBg: string;
  accentColor: string;
  avatarBg: string;
  hoverBg: string;
  activeClass: string;
  inactiveClass: string;
  mutedTextClass: string;
  mobileTitleLabel: string;
}

export const DEFAULT_SIDEBAR_THEME: Omit<SidebarTheme, 'mobileTitleLabel'> = {
  sidebarBg: 'bg-app-sidebar',
  accentColor: 'bg-gradient-to-br from-primary-400 to-primary-600',
  avatarBg: 'bg-primary-700',
  hoverBg: 'hover:bg-app-sidebar-hover',
  activeClass: 'bg-primary-600/15 text-primary-300 border-l-2 border-primary-400',
  inactiveClass:
    'text-app-sidebar-text hover:bg-app-sidebar-hover hover:text-white border-l-2 border-transparent',
  mutedTextClass: 'text-app-sidebar-text-muted',
};
