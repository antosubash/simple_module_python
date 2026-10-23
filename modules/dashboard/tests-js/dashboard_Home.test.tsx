import { configureI18n, keys } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });
vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  usePage: () => ({ props: { menus: {} } }),
}));

import Home from '../dashboard/pages/Home';

const props: ComponentProps<typeof Home> = {
  welcome: 'Welcome back',
  can_view_stats: true,
  total_users: 12,
  active_users_7d: 7,
  users_created_this_month: 2,
  module_count: 1,
  system_info: {
    modules: [
      { name: 'Mail', package: 'mail', status: 'loaded', url: '', admin_url: '', health: '' },
    ],
    python_version: '3.12.4',
    health_checks: [],
  },
};

describe('dashboard Home', () => {
  it('mounts the stats and system module deck', () => {
    render(<Home {...props} />);
    expect(screen.getByRole('heading', { name: keys.dashboard.home.title })).toBeInTheDocument();
    expect(screen.getByText(keys.dashboard.home.stats.total_users)).toBeInTheDocument();
    expect(screen.getByText('mail')).toBeInTheDocument();
  });

  it('mounts only the welcome content without stats permission', () => {
    render(<Home {...props} can_view_stats={false} />);
    expect(screen.getByText('Welcome back')).toBeInTheDocument();
    expect(screen.queryByText(keys.dashboard.home.stats.total_users)).toBeNull();
    expect(screen.queryByText('mail')).toBeNull();
  });
});
