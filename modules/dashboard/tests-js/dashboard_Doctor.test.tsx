import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });
const post = vi.hoisted(() => vi.fn());
vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  router: { post },
  usePage: () => ({ props: {} }),
}));

import type { DoctorProps } from '../dashboard/pages/components/doctor/types';
import Doctor from '../dashboard/pages/Doctor';

const props: DoctorProps = {
  checks: [{ id: 'pages', status: 'pass', command: null, findings: [] }],
  checks_available: true,
  migrations: [{ id: 'a3f1beef', module: 'users', message: 'add invite table', applied: true }],
  migration_commands: { generate: 'make migration', apply: 'make migrate' },
  dev_server: { running: true, rows: [{ name: 'vite', value: ':5050' }] },
  pages_routed: 26,
  stats: {
    checks_passing: 1,
    checks_total: 1,
    modules_loaded: 12,
    pending_migrations: 0,
    python_version: '3.12.4',
  },
};

describe('dashboard Doctor', () => {
  it.each([true, false])('mounts with diagnostics available=%s', (checks_available) => {
    render(<Doctor {...props} checks_available={checks_available} />);
    expect(screen.getByRole('heading', { name: keys.dashboard.doctor.title })).toBeInTheDocument();
    expect(screen.getByTitle('a3f1beef')).toHaveTextContent('a3f1');
    expect(screen.getAllByText(':5050').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: keys.dashboard.doctor.rerun }));
    expect(post).toHaveBeenCalledWith('/admin/doctor/rerun');
  });
});
