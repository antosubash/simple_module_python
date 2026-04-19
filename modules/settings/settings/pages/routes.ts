export const ROUTES = {
  browse: '/settings',
  create: '/settings/create',
  edit: (id: number) => `/settings/${id}/edit`,
  byId: (id: number) => `/settings/${id}`,
} as const;
