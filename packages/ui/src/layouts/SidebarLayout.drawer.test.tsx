import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@inertiajs/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@inertiajs/react')>()),
  usePage: () => ({
    url: '/admin/settings',
    props: {
      menus: {
        adminSidebar: [
          { label: 'One', url: '/admin/one', icon: 'settings' },
          { label: 'Two', url: '/admin/two', icon: 'settings' },
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
  // jsdom lays nothing out, so every element would read as invisible to the
  // trap's visibility filter.
  beforeEach(() => {
    vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([
      {},
    ] as unknown as DOMRectList);
  });

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

describe('SidebarLayout closed drawer accessibility (#638)', () => {
  it('makes a closed phone drawer inert and hides it from assistive technology', () => {
    render(
      <AdminLayout>
        <p>page</p>
      </AdminLayout>,
    );
    const drawer = document.querySelector('aside');
    expect(drawer).toHaveAttribute('inert');
    expect(drawer).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByRole('link', { name: 'One' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'open' }));
    expect(drawer).not.toHaveAttribute('inert');
    expect(drawer).not.toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByRole('link', { name: 'One' })).toBeInTheDocument();

    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    expect(drawer).toHaveAttribute('inert');
    expect(drawer).toHaveAttribute('aria-hidden', 'true');
  });

  it('keeps the desktop sidebar accessible and updates a closed drawer on resize', () => {
    const listeners = new Set<(event: MediaQueryListEvent) => void>();
    const media = {
      matches: true,
      addEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) =>
        listeners.add(listener),
      removeEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) =>
        listeners.delete(listener),
    };
    vi.stubGlobal('matchMedia', () => media);
    try {
      render(
        <AdminLayout>
          <p>page</p>
        </AdminLayout>,
      );
      const drawer = document.querySelector('aside');
      expect(drawer).not.toHaveAttribute('inert');
      expect(screen.getByRole('link', { name: 'One' })).toBeInTheDocument();
      act(() => {
        media.matches = false;
        for (const listener of listeners) listener({ matches: false } as MediaQueryListEvent);
      });
      expect(drawer).toHaveAttribute('inert');
      expect(drawer).toHaveAttribute('aria-hidden', 'true');
      act(() => {
        media.matches = true;
        for (const listener of listeners) listener({ matches: true } as MediaQueryListEvent);
      });
      expect(drawer).not.toHaveAttribute('inert');
      expect(screen.getByRole('link', { name: 'One' })).toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

it.each(['/admin', '/admin/settings/', '/admin/settings/store', '/admin/feature-flags/'])(
  'closes the persistent drawer after navigating to %s',
  (url) => {
    const trigger = setup();
    act(() => {
      document.dispatchEvent(new CustomEvent('inertia:navigate', { detail: { page: { url } } }));
    });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    // Same-URL visits must close it too; a URL dependency alone misses these.
    fireEvent.click(trigger);
    act(() => {
      document.dispatchEvent(new CustomEvent('inertia:navigate', { detail: { page: { url } } }));
    });
    expect(screen.queryByRole('dialog')).toBeNull();
  },
);

it('reports the drawer state and identifies the controlled sidebar', () => {
  const trigger = setup();
  expect(trigger).toHaveAttribute('aria-expanded', 'true');
  expect(trigger).toHaveAttribute('aria-controls', screen.getByRole('dialog').id);
  fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
  expect(trigger).toHaveAttribute('aria-expanded', 'false');
});

it('keeps Back to app outside the scrolling navigation', () => {
  setup();
  const back = screen.getByRole('link', { name: 'back_to_app' });
  expect(screen.getByRole('navigation')).not.toContainElement(back);
  expect(back.parentElement?.parentElement?.parentElement).toHaveClass('shrink-0');
});
