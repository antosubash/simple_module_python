import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@inertiajs/react', () => ({
  usePage: () => ({ url: '/admin/settings', props: {} }),
  Link: ({
    href,
    children,
    ...rest
  }: { href: string; children: React.ReactNode } & Record<string, unknown>) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock('next-themes', () => ({ useTheme: () => ({ theme: 'light' }) }));

vi.mock('@simple-module-py/i18n', () => {
  const keys = new Proxy({}, { get: () => new Proxy({}, { get: () => 'k' }) });
  return { useT: () => ({ t: (k: string) => k }), t: (k: string) => k, keys };
});

vi.mock('../components/AppTopbar', () => ({
  AppTopbar: () => null,
  activeSection: () => null,
  findSection: () => null,
}));
vi.mock('../components/BrandingFooter', () => ({ BrandingFooter: () => null }));
vi.mock('../components/BrandingHead', () => ({ BrandingHead: () => null }));
vi.mock('../components/BrandingBanner', () => ({ BrandingBanner: () => null }));
vi.mock('../components/DemoBanner', () => ({ DemoBanner: () => null }));
vi.mock('./MobileBar', () => ({ MobileBar: () => null }));
vi.mock('./SidebarUserMenu', () => ({ SidebarUserMenu: () => null }));

import { toast } from 'sonner';
import { AdminLayout } from './AdminLayout';
import { AuthenticatedLayout } from './AuthenticatedLayout';

describe('AdminLayout toasts', () => {
  it('renders a toast fired from an admin page', async () => {
    render(
      <AdminLayout>
        <p>page</p>
      </AdminLayout>,
    );
    await act(async () => {
      toast.error('Managed key refused');
    });
    expect(await screen.findByText('Managed key refused')).toBeTruthy();
    expect(document.querySelectorAll('[data-sonner-toaster]').length).toBe(1);
  });

  it('mounts exactly one toaster in the app layout too', async () => {
    render(
      <AuthenticatedLayout>
        <p>page</p>
      </AuthenticatedLayout>,
    );
    await act(async () => {
      toast.success('Saved from the app layout');
    });
    expect(await screen.findByText('Saved from the app layout')).toBeTruthy();
    expect(document.querySelectorAll('[data-sonner-toaster]').length).toBe(1);
  });
});

describe('SidebarLayout skip link', () => {
  it('renders a skip link as the first focusable element targeting #main', () => {
    render(
      <AdminLayout>
        <p>page</p>
      </AdminLayout>,
    );
    const link = document.querySelector('a[href="#main"]') as HTMLElement;
    expect(link.getAttribute('href')).toBe('#main');
    expect(link.className).toContain('sr-only');
    expect(link.className).toContain('focus:not-sr-only');
    expect(document.querySelector('a[href], button, [tabindex="0"]')).toBe(link);
    const main = document.getElementById('main');
    expect(main?.getAttribute('tabindex')).toBe('-1');
    expect(main?.textContent).toContain('page');
  });
});
