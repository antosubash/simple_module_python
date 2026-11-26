import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { beforeEach, expect, test, vi } from 'vitest';
import Edit from '../users/pages/Users/Edit';
import Index from '../users/pages/Users/Index';

vi.mock('@inertiajs/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@inertiajs/react')>()),
  Head: () => null,
  Link: ({ children, ...props }: React.ComponentProps<'a'>) => <a {...props}>{children}</a>,
  usePage: () => ({ url: '/admin/users/user-1', props: { auth: { permissions: [] } } }),
}));

beforeEach(() =>
  configureI18n({
    locale: 'en',
    messages: {
      'users.index.search_label': 'Search people',
      'users.index.add_people': 'Add people',
      'users.edit.subtitle': '{email} · joined {joined} · last login {lastLogin}',
    },
  }),
);

const user: ComponentProps<typeof Edit>['user'] = {
  id: 'user-1',
  email: `${'long'.repeat(20)}@example.com`,
  full_name: null,
  roles: [],
  is_active: true,
  is_verified: true,
  is_external: false,
  last_login_at: null,
  created_at: null,
  invited_at: null,
  invite_expires_at: null,
  state: 'active',
};

function edit() {
  return render(
    <Edit
      user={user}
      roles={[]}
      has_permissions_module
      recent_activity={[
        { at: '2026-11-26T12:00:00Z', summary: 'Changed settings', href: '/activity/1' },
      ]}
      linked_sign_ins={[
        {
          id: 'link-1',
          provider: 'Microsoft',
          username: null,
          subject: null,
          last_sign_in_at: null,
        },
      ]}
      has_duplicate_linked_sign_ins={false}
    />,
  );
}

test('user edit sections follow h1 with h2, including linked sign-ins', () => {
  edit();
  const headings = screen.getAllByRole('heading');
  expect(headings[0]).toHaveTextContent(user.email);
  expect(headings.map((heading) => heading.tagName)).toEqual(['H1', 'H2', 'H2', 'H2', 'H2', 'H2']);
});

test('a long identity can wrap inside the user edit heading', () => {
  edit();
  expect(screen.getByRole('heading', { level: 1 })).toHaveClass('[overflow-wrap:anywhere]');
});

test('permissions and activity links have narrow/coarse touch targets', () => {
  edit();
  for (const link of screen.getAllByRole('link')) {
    expect(link).toHaveClass('max-lg:min-h-11', 'pointer-coarse:min-h-11');
  }
});

test('the people filter has a translated name and add-people keeps a touch target', () => {
  render(
    <Index
      users={[user]}
      roles={[]}
      query=""
      pagination={{ page: 1, per_page: 20, total: 1 }}
      aggregates={{ active: 1, unverified: 0, invited: 0 }}
      filters={{ status: 'all', role: '', verified: 'all', sort: 'email', order: 'asc' }}
    />,
  );
  expect(screen.getByRole('searchbox', { name: 'Search people' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Add people' })).toHaveClass(
    'max-lg:min-h-11',
    'pointer-coarse:min-h-11',
  );
  for (const heading of screen.getAllByRole('columnheader')) {
    expect(heading).toHaveClass('max-lg:text-xs');
  }
});

test('the long email also wraps in the user edit subtitle', () => {
  edit();
  expect(screen.getByText(`${user.email} · joined`, { exact: false })).toHaveClass(
    '[overflow-wrap:anywhere]',
  );
});
