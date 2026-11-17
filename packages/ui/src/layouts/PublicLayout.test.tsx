import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MenuItem } from '../types';

const { navbar } = vi.hoisted(() => ({ navbar: [] as MenuItem[] }));

vi.mock('@inertiajs/react', () => ({
  usePage: () => ({
    props: {
      auth: { user: null, isAuthenticated: true, permissions: [] },
      menus: { navbar, sidebar: [], adminSidebar: [], userDropdown: [] },
      homeUrl: '/home/',
    },
  }),
  Head: () => null,
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock('@simple-module-py/i18n', () => ({
  useT: () => ({ t: (key: string) => key }),
  keys: {
    ui: {
      public_nav: {
        open_dashboard: 'Open dashboard',
        sign_in: 'Sign in',
        open_menu: 'Open menu',
        close_menu: 'Close menu',
      },
    },
  },
}));

vi.mock('../components/BrandingFooter', () => ({ BrandingFooter: () => null }));

import { PublicLayout } from './PublicLayout';

describe('PublicLayout', () => {
  beforeEach(() => {
    navbar.length = 0;
  });

  it('links the signed-in entry to the homeUrl shared prop', () => {
    render(
      <PublicLayout>
        <p>body</p>
      </PublicLayout>,
    );
    const links = screen.getAllByRole('link').filter((a) => a.getAttribute('href') === '/home/');
    expect(links.length).toBeGreaterThan(0);
    expect(document.querySelector('a[href="/dashboard/"]')).toBeNull();
  });

  it('renders navbar items in both the desktop navigation and mobile menu', () => {
    navbar.push({ label: 'Help center', url: '/help', icon: 'info' });
    render(<PublicLayout>body</PublicLayout>);
    const nav = within(screen.getByRole('navigation'));

    const desktopLink = nav.getByRole('link', { name: 'Help center' });
    expect(desktopLink).toHaveAttribute('href', '/help');
    expect(desktopLink.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');

    fireEvent.click(nav.getByRole('button', { name: 'Open menu' }));
    const [desktop, mobileLink] = nav.getAllByRole('link', { name: 'Help center' });
    expect(desktop).toBe(desktopLink);
    expect(mobileLink).toHaveAttribute('href', '/help');
    mobileLink.addEventListener('click', (event) => event.preventDefault());
    fireEvent.click(mobileLink);
    expect(nav.getByRole('link', { name: 'Help center' })).toBe(desktopLink);
  });

  it('keeps framework links out of an empty navbar', () => {
    render(<PublicLayout>body</PublicLayout>);
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual([
      '/',
      '/home/',
    ]);
  });
});
