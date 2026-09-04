import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { MenuItem } from '../types';

vi.mock('@inertiajs/react', () => ({
  usePage: () => ({
    url: '/dashboard/',
    props: { i18n: { locale: 'en', supportedLocales: ['en'], messages: {} } },
  }),
  router: { visit: vi.fn(), post: vi.fn() },
  Link: ({
    href,
    method,
    as: renderAs,
    children,
    ...rest
  }: {
    href: string;
    method?: string;
    as?: string;
    children: React.ReactNode;
  } & Record<string, unknown>) =>
    renderAs === 'button' ? (
      <button type="button" data-href={href} data-method={method} {...rest}>
        {children}
      </button>
    ) : (
      <a href={href} {...rest}>
        {children}
      </a>
    ),
}));

vi.mock('@simple-module-py/i18n', () => {
  const labels: Record<string, string> = {
    'ui.topbar.log_out': 'Log out',
    'ui.switcher.label': 'Change language',
    'ui.switcher.single_locale': 'Only EN is enabled',
    'ui.command_palette.trigger': 'Search',
  };
  return {
    useT: () => ({ t: (key: string) => labels[key] ?? key }),
    keys: {
      ui: {
        topbar: { log_out: 'ui.topbar.log_out' },
        switcher: { label: 'ui.switcher.label', single_locale: 'ui.switcher.single_locale' },
        command_palette: {
          trigger: 'ui.command_palette.trigger',
          title: 'ui.command_palette.title',
          description: 'ui.command_palette.description',
          placeholder: 'ui.command_palette.placeholder',
          empty: 'ui.command_palette.empty',
        },
        nav_groups: {
          navigation: 'ui.nav_groups.navigation',
          account: 'ui.nav_groups.account',
        },
      },
    },
  };
});

import { AppTopbar, activeSection } from './AppTopbar';

const item = (label: string, url: string): MenuItem => ({ label, url, icon: 'grid' });

const NAV: MenuItem[] = [
  item('Dashboard', '/dashboard/'),
  item('Users', '/users/admin'),
  item('Files', '/file_storage'),
  item('Background tasks', '/admin/background-tasks'),
];

describe('activeSection', () => {
  it('matches a section on its own index', () => {
    expect(activeSection(NAV, '/users/admin')?.label).toBe('Users');
  });

  it('claims sub-pages for their section', () => {
    expect(activeSection(NAV, '/users/admin/add')?.label).toBe('Users');
    expect(activeSection(NAV, '/admin/background-tasks/workers')?.label).toBe('Background tasks');
  });

  it('keeps query strings from breaking the match', () => {
    expect(activeSection(NAV, '/file_storage?q=logo')?.label).toBe('Files');
  });

  it('matches the absolute url Inertia actually reports', () => {
    // page.url arrives as http://host:port/path, not a bare path.
    expect(activeSection(NAV, 'http://localhost:8300/users/admin/add')?.label).toBe('Users');
  });

  it('prefers the longest match when one entry prefixes another', () => {
    // A shorter entry sharing a prefix must not steal the deeper section.
    const nav = [item('Admin', '/admin'), item('Background tasks', '/admin/background-tasks')];
    expect(activeSection(nav, '/admin/background-tasks/workers')?.label).toBe('Background tasks');
  });

  it('returns null for a page outside every section', () => {
    // Permissions pages are sub-pages of another module and register no menu
    // entry — the crumb falls back to the page heading alone rather than
    // inventing a section.
    expect(activeSection(NAV, '/permissions/roles/editor')).toBeNull();
  });

  it('returns null when the user can see no entries at all', () => {
    expect(activeSection([], '/users/admin')).toBeNull();
  });
});

const LOGOUT: MenuItem = {
  label: 'Logout',
  url: '/users/logout',
  icon: 'log-out',
  method: 'post',
};
const PROFILE: MenuItem = { label: 'Profile', url: '/users/profile', icon: 'user' };

describe('AppTopbar log out', () => {
  it('submits the account menu’s post item as a button', () => {
    render(
      <AppTopbar
        navItems={NAV}
        accountItems={[PROFILE, LOGOUT]}
        currentUrl="/dashboard/"
        activeMenuItem={null}
      />,
    );
    const button = screen.getByRole('button', { name: 'Log out' });
    expect(button).toHaveAttribute('data-method', 'post');
    expect(button).toHaveAttribute('data-href', '/users/logout');
  });

  it('prefers the log-out item over another post action', () => {
    const bulk: MenuItem = {
      label: 'Clear cache',
      url: '/admin/cache/clear',
      icon: 'trash',
      method: 'post',
    };
    render(
      <AppTopbar
        navItems={NAV}
        accountItems={[PROFILE, bulk, LOGOUT]}
        currentUrl="/dashboard/"
        activeMenuItem={null}
      />,
    );
    expect(screen.getByRole('button', { name: 'Log out' })).toHaveAttribute(
      'data-href',
      '/users/logout',
    );
  });

  it('renders no log out control when the menu has no post item', () => {
    render(
      <AppTopbar
        navItems={NAV}
        accountItems={[PROFILE]}
        currentUrl="/dashboard/"
        activeMenuItem={null}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Log out' })).toBeNull();
  });
});
