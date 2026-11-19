import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  usePage: () => ({ url: '/admin/permissions/', props: {} }),
}));

import Browse from '../permissions/pages/Browse';

configureI18n({
  locale: 'en',
  messages: {
    'permissions.browse.title': 'Permissions',
    'permissions.browse.roles_heading': 'Roles',
    'permissions.browse.users_heading': 'Users',
    'permissions.browse.edit_link': 'Edit',
    'permissions.browse.external_roles': 'Roles are managed by your identity provider.',
  },
});

test('external roles link to permission mappings without local assignment controls', () => {
  render(
    <Browse
      roles={[
        { id: 'role-id', name: 'editor', label: 'Content editor', description: null, count: 2 },
      ]}
      users={[{ id: 'user-id', email: 'idp@test', full_name: null, count: 1 }]}
      query=""
      roles_editable={false}
    />,
  );
  expect(screen.getByText('Content editor')).toBeVisible();
  expect(screen.getByText('Roles are managed by your identity provider.')).toBeVisible();
  expect(
    screen.getAllByRole('link', { name: 'Edit' }).map((link) => link.getAttribute('href')),
  ).toEqual(['/admin/permissions/roles/role-id/edit', '/admin/permissions/users/user-id/edit']);
  expect(
    screen.queryByRole('link', { name: /assign|create|users admin/i }),
  ).not.toBeInTheDocument();
});
