import type { VisitOptions } from '@inertiajs/core';
import { router } from '@inertiajs/react';
import { configureI18n } from '@simple-module-py/i18n';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import en from '../users/locales/en.json';
import Edit from '../users/pages/Users/Edit';

vi.mock('@inertiajs/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@inertiajs/react')>()),
  Head: () => null,
  usePage: () => ({ props: { auth: { permissions: [] } } }),
}));
vi.mock('@simple-module-py/ui/components/PageShell', () => ({
  PageShell: ({ children, actions }: { children: ReactNode; actions: ReactNode }) => (
    <main>
      {actions}
      {children}
    </main>
  ),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const props = {
  user: {
    id: 'user-1',
    email: 'jane@example.com',
    full_name: 'Jane',
    roles: [],
    is_active: true,
    is_verified: true,
    is_external: false,
    last_login_at: null,
    created_at: null,
    invited_at: null,
    invite_expires_at: null,
    state: 'active' as const,
  },
  roles: [],
  has_permissions_module: false,
  recent_activity: null,
  linked_sign_ins: [
    {
      id: 'link-1',
      provider: 'Microsoft',
      username: null,
      subject: null,
      last_sign_in_at: null,
    },
  ],
  has_duplicate_linked_sign_ins: false,
};
const partial = ['linked_sign_ins', 'has_duplicate_linked_sign_ins'];

function visit(path: string, method = 'get', options: VisitOptions = {}) {
  return document.dispatchEvent(
    new CustomEvent('inertia:before', {
      cancelable: true,
      detail: {
        visit: {
          url: new URL(path, window.location.href),
          method,
          prefetch: false,
          preserveState: false,
          only: [],
          ...options,
        },
      },
    }),
  );
}

beforeEach(() => {
  const messages: Record<string, string> = {};
  function flatten(value: object, prefix = 'users') {
    for (const [key, child] of Object.entries(value)) {
      if (typeof child === 'string') messages[`${prefix}.${key}`] = child;
      else flatten(child, `${prefix}.${key}`);
    }
  }
  flatten(en);
  configureI18n({ locale: 'en', messages });
  window.history.replaceState(null, '', '/admin/users/user-1');
  vi.spyOn(window, 'confirm').mockReturnValue(false);
});
afterEach(() => vi.restoreAllMocks());

test('removing the final link keeps unsaved details and focuses the mounted card heading', async () => {
  const remove = vi.fn((url, options) => visit(String(url), 'delete', options));
  vi.spyOn(router, 'delete').mockImplementation(remove);
  const { rerender } = render(<Edit {...props} />);
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Unsaved name' } });
  fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove' }));
  expect(window.confirm).not.toHaveBeenCalled();
  rerender(<Edit {...props} linked_sign_ins={[]} />);
  const options = remove.mock.calls[0][1];
  // The network/page boundary is replaced; the page, guard and dialog are real.
  await act(async () => {
    await options.onSuccess();
    options.onFinish();
  });
  expect(screen.getByLabelText('Full name')).toHaveValue('Unsaved name');
  await waitFor(() =>
    expect(screen.getByRole('heading', { name: 'Linked sign-ins' })).toHaveFocus(),
  );
  expect(visit('/admin/users/')).toBe(false);
  expect(window.confirm).toHaveBeenCalled();
});

test('an initially unlinked account has no empty linked-sign-ins card', () => {
  render(<Edit {...props} linked_sign_ins={[]} />);
  expect(screen.queryByRole('heading', { name: 'Linked sign-ins' })).not.toBeInTheDocument();
});

test.each([
  { path: '/admin/users/user-1', method: 'get', only: partial, preserveState: true, allowed: true },
  {
    path: '/admin/users/user-1/linked-sign-ins/link-1',
    method: 'delete',
    only: partial,
    preserveState: true,
    allowed: true,
  },
  {
    path: '/admin/users/user-2/linked-sign-ins/link-1',
    method: 'delete',
    only: partial,
    preserveState: true,
    allowed: false,
  },
  {
    path: '/admin/users/user-2',
    method: 'get',
    only: partial,
    preserveState: true,
    allowed: false,
  },
  {
    path: '/admin/users/user-1',
    method: 'get',
    only: ['user'],
    preserveState: true,
    allowed: false,
  },
  { path: '/admin/users/user-1', method: 'get', only: [], preserveState: true, allowed: false },
  {
    path: '/admin/users/user-1',
    method: 'get',
    only: partial,
    preserveState: false,
    allowed: false,
  },
  {
    path: '/admin/users/user-1/linked-sign-ins/link-1/other',
    method: 'delete',
    only: partial,
    preserveState: true,
    allowed: false,
  },
])(
  'dirty form guard: $method $path, $only, preserveState=$preserveState',
  ({ path, method, only, preserveState, allowed }) => {
    render(<Edit {...props} />);
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Unsaved name' } });
    expect(visit(path, method, { only, preserveState })).toBe(allowed);
    expect(window.confirm).toHaveBeenCalledTimes(allowed ? 0 : 1);
  },
);
