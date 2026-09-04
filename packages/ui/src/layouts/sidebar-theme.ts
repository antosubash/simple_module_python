/**
 * The sidebar's visual language, shared by every sidebar-driven layout.
 *
 * Split from SidebarLayout so the palette is a data concern with one home:
 * AdminLayout and AuthenticatedLayout both spread the default and override
 * only what makes their shell theirs, so a tweak lands once instead of
 * drifting between the two shells.
 */

/**
 * The sidebar is near-black in every theme, where Button's default
 * `ring-ring/50` is effectively invisible — icon-only toggles there are
 * reachable by keyboard, so they get a light ring that actually shows
 * (WCAG 2.4.7). Text links beside them fall back to the UA outline, which
 * already reads on this surface.
 */
export const SIDEBAR_ICON_FOCUS = 'focus-visible:ring-white/70 focus-visible:border-white/70';

export interface SidebarTheme {
  sidebarBg: string;
  accentColor: string;
  hoverBg: string;
  activeClass: string;
  inactiveClass: string;
  mutedTextClass: string;
  mobileTitleLabel: string;
}

export const DEFAULT_SIDEBAR_THEME: Omit<SidebarTheme, 'mobileTitleLabel'> = {
  sidebarBg: 'bg-app-sidebar',
  accentColor: 'bg-gradient-to-br from-primary-400 to-primary-600',
  hoverBg: 'hover:bg-app-sidebar-hover',
  // Solid pill, per the deck: a tinted row with a left rule read as a hover
  // state next to the near-black surface, and lost the current page at a
  // glance on a phone.
  activeClass: 'bg-primary text-white',
  inactiveClass: 'text-app-sidebar-text hover:bg-app-sidebar-hover hover:text-white',
  mutedTextClass: 'text-app-sidebar-text-muted',
};
