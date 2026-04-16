export interface MenuItem {
  label: string;
  url: string;
  icon: string;
  method?: 'get' | 'post';
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
  csrf_token?: string;
}
