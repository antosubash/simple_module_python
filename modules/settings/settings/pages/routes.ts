export const ROUTES = {
  /** Per-module forms — the section root, and where "Settings" now lands. */
  modules: '/admin/settings/',
  /** Raw key/value store, demoted from the root. */
  browse: '/admin/settings/store',
  create: '/admin/settings/create',
  edit: (id: number) => `/admin/settings/${id}/edit`,
  byId: (id: number) => `/admin/settings/${id}`,
  testConnection: (pkg: string) => `/admin/settings/test-connection/${pkg}`,
} as const;
