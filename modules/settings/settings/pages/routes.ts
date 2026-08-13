export const ROUTES = {
  /** Per-module forms — the section root, and where "Settings" now lands. */
  modules: '/settings/',
  /** Raw key/value store, demoted from the root. */
  browse: '/settings/store',
  create: '/settings/create',
  edit: (id: number) => `/settings/${id}/edit`,
  byId: (id: number) => `/settings/${id}`,
  testConnection: (pkg: string) => `/settings/test-connection/${pkg}`,
} as const;
