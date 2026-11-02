import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import type { MenuItem } from '../types';

vi.mock('@inertiajs/react', () => ({
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('./AdminSectionLink', () => ({ AdminSectionLink: () => <a href="/admin">admin</a> }));

import { TooltipProvider } from '../components/ui/tooltip';
import { SidebarNav } from './SidebarNav';
import { DEFAULT_SIDEBAR_THEME } from './sidebar-theme';

const theme = { ...DEFAULT_SIDEBAR_THEME, mobileTitleLabel: 'App' };
const items: MenuItem[] = [
  { label: 'Home', url: '/', icon: 'home' },
  { label: 'Users', url: '/users/', icon: 'users', group: 'Access' },
  { label: 'Roles', url: '/roles/', icon: 'users', group: 'Access' },
];

function renderNav(props: Partial<React.ComponentProps<typeof SidebarNav>> = {}) {
  return render(
    <TooltipProvider>
      <SidebarNav
        menuItems={items}
        adminItems={[]}
        active={items[1]}
        theme={theme}
        showAdminLink={false}
        onNavigate={() => {}}
        {...props}
      />
    </TooltipProvider>,
  );
}

describe('SidebarNav', () => {
  test('renders one header per named group and every item', () => {
    renderNav();
    expect(screen.getAllByText('Access')).toHaveLength(1);
    for (const item of items) expect(screen.getByRole('link', { name: item.label })).toBeVisible();
  });

  test('highlights only the active item', () => {
    renderNav();
    expect(screen.getByRole('link', { name: 'Users' }).className).toContain(theme.activeClass);
    expect(screen.getByRole('link', { name: 'Roles' }).className).not.toContain(theme.activeClass);
  });

  test('shows the admin link and the footer slot only when asked', () => {
    const { rerender } = renderNav();
    expect(screen.queryByRole('link', { name: 'admin' })).toBeNull();
    rerender(
      <TooltipProvider>
        <SidebarNav
          menuItems={items}
          adminItems={[]}
          active={null}
          theme={theme}
          showAdminLink
          onNavigate={() => {}}
        >
          <span>slot</span>
        </SidebarNav>
      </TooltipProvider>,
    );
    expect(screen.getByRole('link', { name: 'admin' })).toBeVisible();
    expect(screen.getByText('slot')).toBeVisible();
  });
});
