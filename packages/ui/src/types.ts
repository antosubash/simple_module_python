export interface MenuItem {
  label: string;
  url: string;
  icon: string;
  method?: 'get' | 'post';
  group?: string;
}

export interface BrandingShared {
  appName: string;
  primaryColor: string | null;
  /** Selected design pack slug; the site root class is `${designPack}-root`. */
  designPack: string | null;
  logoUrl: string | null;
  faviconUrl: string | null;
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
  // Injected by the branding module's shared-props provider (optional: the
  // module may not be installed).
  branding?: BrandingShared;
}
