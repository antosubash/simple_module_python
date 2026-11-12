import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

const props = vi.hoisted(() => ({ menus: { adminSidebar: [] as unknown[] } }));

vi.mock('@inertiajs/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@inertiajs/react')>()),
  usePage: () => ({ props, url: '/admin' }),
  Head: () => null,
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('@simple-module-py/ui/hooks/usePageProps', () => ({ usePageProps: () => props }));

import Overview from '../simple_module_hosting/admin_overview/pages/Overview';

describe('Admin overview', () => {
  it('shows the empty state when the viewer has no admin tools', () => {
    props.menus.adminSidebar = [];
    render(<Overview />);
    expect(screen.getByText(keys.hosting.admin.empty)).toBeInTheDocument();
  });

  it('renders one card per admin sidebar entry, grouped', () => {
    props.menus.adminSidebar = [
      { label: 'Users', url: '/admin/users', icon: 'users', group: 'Access' },
      { label: 'Settings', url: '/admin/settings', icon: 'settings', group: 'System' },
    ];
    render(<Overview />);
    expect(screen.getByRole('link', { name: /Users/ })).toHaveAttribute('href', '/admin/users');
    expect(screen.getByText('Access')).toBeInTheDocument();
    expect(screen.getByText('System')).toBeInTheDocument();
  });
});
