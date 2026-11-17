import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MenuItem } from '../types';

const { navbar, page } = vi.hoisted(() => ({
  navbar: [] as MenuItem[],
  page: { url: '/help/topics/?q=search#intro' },
}));

vi.mock('@inertiajs/react', () => ({
  usePage: () => ({
    url: page.url,
    props: {
      auth: { user: null, isAuthenticated: true, permissions: [] },
      menus: { navbar, sidebar: [], adminSidebar: [], userDropdown: [] },
      homeUrl: '/home/',
    },
  }),
  Head: () => null,
  Link: ({
    href,
    children,
    as,
    method: _method,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
    as?: string;
    method?: string;
  }) =>
    as === 'button' ? (
      <button type="button" {...rest}>
        {children}
      </button>
    ) : (
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

  it.each([
    { label: 'Email support', url: 'mailto:help@example.com', icon: '' },
    { label: 'Refresh session', url: '/session', method: 'post' as const, icon: '' },
  ])('returns focus to the toggle after keyboard activation of $label', async (item) => {
    navbar.push(item);
    const user = userEvent.setup();
    render(<PublicLayout>body</PublicLayout>);
    const nav = within(screen.getByRole('navigation'));
    const toggle = nav.getByRole('button', { name: 'Open menu' });
    toggle.focus();
    await user.keyboard('{Enter}');
    const items = nav.getAllByRole(item.method === 'post' ? 'button' : 'link', {
      name: item.label,
    });
    const mobileItem = items[1];
    mobileItem.addEventListener('click', (event) => event.preventDefault());
    mobileItem.focus();
    await user.keyboard('{Enter}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveFocus();
  });

  it('preserves focus when activation moves it outside the mobile menu', () => {
    navbar.push({ label: 'Help center', url: '/help', icon: '' });
    render(
      <PublicLayout>
        <button type="button">Content target</button>
      </PublicLayout>,
    );
    const nav = within(screen.getByRole('navigation'));
    fireEvent.click(nav.getByRole('button', { name: 'Open menu' }));
    const target = screen.getByRole('button', { name: 'Content target' });
    const mobileLink = nav.getAllByRole('link', { name: 'Help center' })[1];
    mobileLink.addEventListener('click', (event) => {
      event.preventDefault();
      target.focus();
    });
    mobileLink.focus();
    fireEvent.click(mobileLink);
    expect(nav.getByRole('button', { name: 'Open menu' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(target).toHaveFocus();
  });

  it.each(['/help/topics/?q=search#intro', 'https://local.example/help/topics/?q=search'])(
    'marks only the matching internal GET entry active for %s on desktop and mobile',
    (url) => {
      page.url = url;
      navbar.push(
        { label: 'Help', url: '/help/', icon: '' },
        { label: 'Other', url: '/helpful', icon: '' },
        { label: 'External', url: 'https://example.com/help/topics', icon: '' },
        { label: 'Protocol relative', url: '//example.com/help/topics', icon: '' },
        { label: 'Action', url: '/help/topics/', method: 'post', icon: '' },
        { label: 'Topics', url: '/help/topics', method: 'get', icon: '' },
      );
      render(<PublicLayout>body</PublicLayout>);
      const nav = within(screen.getByRole('navigation'));
      fireEvent.click(nav.getByRole('button', { name: 'Open menu' }));
      for (const link of nav.getAllByRole('link', { name: 'Topics' })) {
        expect(link).toHaveAttribute('aria-current', 'page');
        expect(link).toHaveClass('text-foreground', 'font-medium');
      }
      for (const name of ['Help', 'Other', 'External', 'Protocol relative']) {
        for (const link of nav.getAllByRole('link', { name })) {
          expect(link).not.toHaveAttribute('aria-current');
          expect(link).toHaveClass('text-muted-foreground');
        }
      }
      for (const action of nav.getAllByRole('button', { name: 'Action' })) {
        expect(action).not.toHaveAttribute('aria-current');
        expect(action).toHaveClass('text-muted-foreground');
      }
    },
  );

  it('keeps framework links out of an empty navbar', () => {
    render(<PublicLayout>body</PublicLayout>);
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual([
      '/',
      '/home/',
    ]);
  });
});
