import '@testing-library/jest-dom/vitest';
import { router } from '@inertiajs/react';
import { configureI18n } from '@simple-module-py/i18n';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import Members from '../tenants/pages/Members';

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  usePage: () => ({ url: '/tenants/members' }),
  router: { get: vi.fn(), reload: vi.fn() },
}));
configureI18n({
  locale: 'en',
  messages: {
    'ui.pagination.next': 'Next',
    'ui.pagination.previous': 'Previous',
    'ui.pagination.showing': 'Showing {from}–{to} of {total}',
    'tenants.members.remove_button': 'Remove',
    'tenants.members.remove_confirm_confirm': 'Confirm removal',
  },
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

const props = {
  tenant: { id: 'org', slug: 'org', name: 'Org' },
  my_role: 'owner' as const,
  my_user_id: 'owner',
  can_manage: true,
  members: [{ user_id: 'member', email: 'member@x.io', role: 'member' as const, joined_at: null }],
  invitations: [],
  seats: { used: 60, limit: null },
  page: 2,
  per_page: 25,
  total: 60,
};

test('page navigation keeps server page size and uses server clamped page', async () => {
  render(<Members {...props} />);
  expect(screen.getByText('Showing 26–50 of 60')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(router.get).toHaveBeenCalledWith(
    '/tenants/members',
    { page: 3, per_page: 25 },
    { preserveState: true, preserveScroll: true },
  );
  await userEvent.click(screen.getByRole('button', { name: 'Previous' }));
  expect(router.get).toHaveBeenLastCalledWith(
    '/tenants/members',
    { page: 1, per_page: 25 },
    { preserveState: true, preserveScroll: true },
  );
});

test('role mutation reloads the current page and page size', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
  render(<Members {...props} />);
  await userEvent.selectOptions(screen.getAllByRole('combobox')[0], 'admin');
  expect(router.get).toHaveBeenCalledWith(
    '/tenants/members',
    { page: 2, per_page: 25 },
    { preserveState: true, preserveScroll: true },
  );
  vi.unstubAllGlobals();
});
