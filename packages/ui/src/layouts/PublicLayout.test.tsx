import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@inertiajs/react', () => ({
  usePage: () => ({
    props: { auth: { isAuthenticated: true }, branding: null, homeUrl: '/home/' },
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
  keys: { ui: { public_nav: { open_dashboard: 'open_dashboard', sign_in: 'sign_in' } } },
}));

import { PublicLayout } from './PublicLayout';

describe('PublicLayout', () => {
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
});
