export interface MenuItem {
  label: string;
  url: string;
  icon: string;
  method?: 'get' | 'post';
  group?: string;
}

/**
 * `true` when a menu entry must be submitted rather than navigated to (e.g.
 * logout) — visiting it with a GET would silently do nothing. Shared so the
 * declarative (`Link` method/as props) and imperative (`router.post`/
 * `router.visit`) call sites stay in sync as the method matrix grows.
 */
export function isPostMenuItem(item: MenuItem): boolean {
  return item.method === 'post';
}

export interface BrandingShared {
  appName: string;
  primaryColor: string | null;
  // Slug of the site-wide design pack, or null for base tokens only. The
  // public site wraps its document in `${designPack}-root`, which is the hook
  // the owning module's stylesheet selects on.
  designPack: string | null;
  logoUrl: string | null;
  /**
   * Logo variant for the app's always-dark surfaces (the sidebar and mobile
   * bar), where a dark-ink primary logo would be invisible. `null` means none
   * was uploaded — callers fall back to `logoUrl` via `darkSurfaceLogo`.
   */
  logoDarkUrl: string | null;
  faviconUrl: string | null;
  /** Site-wide announcement, or `null` when no message is set. */
  banner: { message: string; severity: string } | null;
}

export interface SharedProps {
  auth: {
    user: { name: string; email: string; roles: string[] } | null;
    isAuthenticated: boolean;
    permissions: string[];
  };
  menus: {
    sidebar: MenuItem[];
    adminSidebar: MenuItem[];
    navbar: MenuItem[];
    userDropdown: MenuItem[];
  };
  // Injected by the users module's shared-props provider. Absent when no local
  // auth provider is installed (e.g. a Keycloak-only deployment), which reads
  // the same as "closed" — the host isn't the one taking signups.
  signup?: { allowed: boolean };
  // Injected by the branding module's shared-props provider (optional: the
  // module may not be installed).
  branding?: BrandingShared;
}
