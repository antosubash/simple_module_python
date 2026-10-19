import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@inertiajs/react', () => ({
  usePage: () => ({
    url: '/admin/settings',
    props: {
      menus: {
        adminSidebar: [
          { label: 'One', url: '/admin/one' },
          { label: 'Two', url: '/admin/two' },
        ],
      },
    },
  }),
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
  const keys = new Proxy(
    {},
    { get: () => new Proxy({}, { get: () => new Proxy({}, { get: (_t, p) => String(p) }) }) },
  );
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
vi.mock('../components/BrandingMark', () => ({ BrandingMark: () => null }));
vi.mock('../components/LocaleSwitcher', () => ({
  LocaleSwitcher: () => null,
  useHasMultipleLocales: () => false,
}));
vi.mock('./SidebarUserMenu', () => ({ SidebarUserMenu: () => null }));
vi.mock('./MobileBar', () => ({
  MobileBar: ({ onOpen }: { onOpen: () => void }) => (
    <button type="button" onClick={onOpen}>
      open
    </button>
  ),
}));

import { AdminLayout } from './AdminLayout';

function setup() {
  render(
    <AdminLayout>
      <p>page</p>
    </AdminLayout>,
  );
  const trigger = screen.getByRole('button', { name: 'open' });
  trigger.focus();
  fireEvent.click(trigger);
  return trigger;
}

describe('SidebarLayout mobile drawer', () => {
  it('is a plain sidebar (no dialog role) until opened', () => {
    render(
      <AdminLayout>
        <p>page</p>
      </AdminLayout>,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.querySelector('aside')?.getAttribute('aria-modal')).toBeNull();
  });

  it('opens as a labelled modal dialog and moves focus inside', () => {
    setup();
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-label')).toBeTruthy();
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it('closes on Escape and returns focus to the trigger', () => {
    const trigger = setup();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('traps Tab and Shift+Tab inside the open drawer', () => {
    setup();
    const dialog = screen.getByRole('dialog');
    const focusables = Array.from(
      dialog.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'),
    );
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    last.focus();
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(last);
  });
});
