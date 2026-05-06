export const STATIC_CHECKS = [
  { name: 'Module imports', status: 'pass' as const, hint: 'All ModuleBase subclasses load.' },
  { name: 'Migration drift', status: 'pass' as const, hint: 'Alembic head matches DB.' },
  { name: 'Orphan pages', status: 'pass' as const, hint: 'Every Inertia page has a route.' },
  {
    name: 'Permission registry',
    status: 'pass' as const,
    hint: 'All declared perms reachable from a role.',
  },
  {
    name: 'Coupling check',
    status: 'warn' as const,
    hint: 'Cross-module imports detected — modules should depend via the registry.',
    file: 'modules/billing/router.py:14',
  },
  {
    name: 'Schema isolation',
    status: 'pass' as const,
    hint: 'No cross-schema foreign keys on Postgres.',
  },
];

export const MIGRATIONS = [
  {
    id: '0024',
    module: 'billing',
    msg: 'create subscriptions table',
    when: 'just now',
    applied: false,
  },
  {
    id: '0023',
    module: 'orders',
    msg: 'add fulfilled_at column',
    when: '3h ago',
    applied: true,
  },
  {
    id: '0022',
    module: 'users',
    msg: 'add invited_by foreign key',
    when: '1d ago',
    applied: true,
  },
  {
    id: '0021',
    module: 'audit',
    msg: 'partition events by month',
    when: '2d ago',
    applied: true,
  },
];

export const ENV_VARS: [string, string][] = [
  ['SM_ENVIRONMENT', 'development'],
  ['SM_DATABASE_URL', 'sqlite+aiosqlite'],
  ['SM_USERS_MAILER', 'console'],
  ['SM_USERS_ALLOW_SIGNUP', 'false'],
];

export const DEV_SERVER: [string, string, 'success' | 'default'][] = [
  ['FastAPI', ':8000', 'success'],
  ['Vite HMR', ':5173', 'success'],
  ['Postgres', ':5432', 'success'],
  ['Worker', 'idle', 'default'],
];

export { TONE } from '@simple-module-py/ui/lib/tone';
