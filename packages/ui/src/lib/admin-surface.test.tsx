import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { withAdminSurface } from './admin-surface';

let destination = '/admin/orders/';
vi.mock('@inertiajs/react', () => ({ usePage: () => ({ url: destination }) }));
afterEach(cleanup);

const Page = Object.assign(() => null, { layout: undefined as unknown });

const surface = {
  prefix: '/admin/orders',
  layout: ({ children }: { children: ReactNode }) => (
    <section aria-label="admin">{children}</section>
  ),
};

it('default layout follows navigation between admin and public URLs', async () => {
  const load = withAdminSurface({ page: async () => ({ default: Page }) }, surface).page;
  await load();
  const layout = Page.layout as (page: ReactNode) => ReactNode;
  const view = render(layout(<div>Content</div>));
  for (const url of ['/admin/orders', '/admin/orders/1?tab=a']) {
    destination = url;
    view.rerender(layout(<div>Content</div>));
    expect(screen.getByRole('region', { name: 'admin' })).toBeTruthy();
  }
  for (const url of ['/orders/login', '/admin/orders-extra']) {
    destination = url;
    view.rerender(layout(<div>Content</div>));
    expect(screen.queryByRole('region', { name: 'admin' })).toBeNull();
    expect(screen.getByText('Content')).toBeTruthy();
  }
  await load();
  expect(Page.layout).toBe(layout);
});

it.each([[], null, [surface.layout], (page: ReactNode) => page])(
  'keeps an explicit page layout',
  async (layout) => {
    Page.layout = layout;
    const load = withAdminSurface({ page: async () => ({ default: Page }) }, surface).page;
    const loaded = await load();
    expect(loaded.default.layout).toBe(layout);
  },
);
