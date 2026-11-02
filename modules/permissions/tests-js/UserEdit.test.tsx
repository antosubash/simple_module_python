import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

// jsdom has no ResizeObserver; Radix's Switch measures its thumb through one.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub);

configureI18n({
  locale: 'en',
  messages: {
    'permissions.user_edit.title': 'Permissions — {email}',
    'permissions.user_edit.head_title': 'Edit User',
    'permissions.user_edit.subtitle':
      '{name} · effective permissions combine role grants and direct grants',
    'permissions.user_edit.subtitle_no_name':
      'Effective permissions combine role grants and direct grants',
    'permissions.user_edit.submit_button': 'Save grants',
    'permissions.user_edit.cancel_link': 'Cancel',
    'permissions.user_edit.roles_label': 'Roles',
    'permissions.user_edit.no_roles': 'No roles assigned',
    'permissions.user_edit.direct_summary': 'Direct grants',
    'permissions.user_edit.effective_summary': 'Effective',
    'permissions.user_edit.legend_direct': 'direct grant',
    'permissions.user_edit.legend_role': 'from role',
    'permissions.user_edit.group_effective': '{granted} effective / {total}',
    'permissions.user_edit.direct_badge': 'direct',
    'permissions.user_edit.via_role': 'granted by {roles}',
    'permissions.user_edit.direct_toggle_label': 'Grant {key} directly to this user',
    'permissions.filters.modules_placeholder': 'Filter modules…',
    'permissions.user_edit.empty': 'No permissions have been registered by any installed module.',
    'permissions.user_edit.no_matches': 'No permissions match this filter.',
  },
});

const mocks = vi.hoisted(() => ({ put: vi.fn() }));

vi.mock('@inertiajs/react', async () => {
  const { useState } = await import('react');
  const sorted = (value: unknown) => JSON.stringify([...(value as string[])].sort());
  return {
    Head: () => null,
    Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
      <a href={href}>{children}</a>
    ),
    router: { on: () => () => {} },
    usePage: () => ({ url: '/admin/permissions/users/u1/edit', props: {} }),
    useForm: (initial: { permissions: string[] }) => {
      const [data, setDataState] = useState(initial);
      return {
        data,
        setData: (key: string, value: string[]) =>
          setDataState((current) => ({ ...current, [key]: value })),
        put: mocks.put,
        processing: false,
        isDirty: sorted(data.permissions) !== sorted(initial.permissions),
        reset: () => setDataState(initial),
      };
    },
  };
});

import UserEdit, { type Props } from '../permissions/pages/UserEdit';

const GROUPS = [
  { name: 'Users', permissions: ['users.delete', 'users.invite', 'users.read', 'users.write'] },
  { name: 'Settings', permissions: ['settings.manage', 'settings.read'] },
];

function renderPage(overrides: Partial<Props> = {}) {
  const props: Props = {
    user: { id: 'u1', email: 'sam@example.com', full_name: 'Sam Okafor' },
    roles: ['editor'],
    direct: ['users.invite', 'settings.manage'],
    inherited: ['users.read', 'users.write', 'users.invite'],
    inherited_by: {
      'users.read': ['editor'],
      'users.write': ['editor', 'admin'],
      'users.invite': ['editor'],
    },
    groups: GROUPS,
    ...overrides,
  };
  return render(<UserEdit {...props} />);
}

// The row is a `<label>` so the whole 44px strip toggles its switch, not just
// the 20px control — `closest('div')` would now walk out to the card body.
const keyRow = (permissionKey: string) =>
  screen.getByText(permissionKey, { selector: 'code' }).closest('label') as HTMLElement;

describe('UserEdit', () => {
  test('renders the deck header, subtitle and actions', () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Permissions — sam@example.com' })).toBeVisible();
    expect(
      screen.getByText('Sam Okafor · effective permissions combine role grants and direct grants'),
    ).toBeVisible();
    expect(screen.getByRole('link', { name: 'Cancel' })).toHaveAttribute('href', '/admin/users/');
    expect(screen.getByRole('button', { name: 'Save grants' })).toBeInTheDocument();
    // The deck's grants screen has no Reset — only Cancel and Save.
    expect(screen.queryByRole('button', { name: /reset|discard/i })).not.toBeInTheDocument();
  });

  test('falls back to the sentence alone when the user has no name', () => {
    renderPage({ user: { id: 'u1', email: 'sam@example.com', full_name: null } });

    expect(
      screen.getByText('Effective permissions combine role grants and direct grants'),
    ).toBeVisible();
  });

  test('summarises roles, direct grants and effective access', () => {
    renderPage();

    expect(screen.getByText('Roles')).toBeVisible();
    expect(screen.getByText('editor')).toBeVisible();
    expect(screen.getByText('Direct grants')).toBeVisible();
    expect(screen.getByText('2')).toBeVisible();
    expect(screen.getByText('4')).toBeVisible();
    expect(screen.getByText('/ 6')).toBeVisible();
  });

  test('shows the direct / from role legend beside the filter', () => {
    renderPage();

    expect(screen.getByPlaceholderText('Filter modules…')).toBeVisible();
    expect(screen.getByText('direct grant')).toBeVisible();
    expect(screen.getByText('from role')).toBeVisible();
  });

  test('counts effective permissions per module', () => {
    renderPage();

    // Each card is a real heading, so a screen reader can navigate module to
    // module rather than meeting a wall of unlabelled regions.
    expect(screen.getByRole('heading', { name: /^Users/ })).toBeVisible();
    expect(screen.getByRole('heading', { name: /^Settings/ })).toBeVisible();

    expect(screen.getByText('3 effective / 4')).toBeVisible();
    expect(screen.getByText('1 effective / 2')).toBeVisible();
  });

  test('badges a role-granted key with its granting role and leaves the switch off', () => {
    renderPage();

    const row = keyRow('users.read');
    expect(within(row).getByText('granted by editor')).toBeVisible();
    expect(within(row).queryByText('direct')).not.toBeInTheDocument();
    expect(within(row).getByRole('switch')).toHaveAttribute('data-state', 'unchecked');
  });

  test('the whole row is the switch\u2019s label, so the tap target is the row', () => {
    renderPage();

    const row = keyRow('users.read');
    expect(row.tagName).toBe('LABEL');
    expect(row).toHaveAttribute('for', within(row).getByRole('switch').id);
    expect(row).toHaveClass('min-h-11');
  });

  test('names every granting role', () => {
    renderPage();

    expect(within(keyRow('users.write')).getByText('granted by editor, admin')).toBeVisible();
  });

  test('badges a directly granted key and shows both badges when a role grants it too', () => {
    renderPage();

    const direct = keyRow('settings.manage');
    expect(within(direct).getByText('direct')).toBeVisible();
    expect(within(direct).queryByText(/granted by/)).not.toBeInTheDocument();
    expect(within(direct).getByRole('switch')).toHaveAttribute('data-state', 'checked');

    const both = keyRow('users.invite');
    expect(within(both).getByText('direct')).toBeVisible();
    expect(within(both).getByText('granted by editor')).toBeVisible();
  });

  test('a key nobody grants is muted and unbadged', () => {
    renderPage();

    const row = keyRow('users.delete');
    expect(within(row).queryByText('direct')).not.toBeInTheDocument();
    expect(within(row).queryByText(/granted by/)).not.toBeInTheDocument();
    expect(screen.getByText('users.delete', { selector: 'code' })).toHaveClass(
      'text-muted-foreground',
    );
  });

  test('the switch grants the key directly and updates the badges and counts', () => {
    renderPage();

    fireEvent.click(
      screen.getByRole('switch', { name: 'Grant users.delete directly to this user' }),
    );

    expect(within(keyRow('users.delete')).getByText('direct')).toBeVisible();
    expect(screen.getByText('4 effective / 4')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Save grants' })).toBeEnabled();
  });

  test('says nothing matched rather than nothing registered', () => {
    renderPage();

    fireEvent.change(screen.getByPlaceholderText('Filter modules…'), {
      target: { value: 'nothing-matches-this' },
    });

    expect(screen.getByText('No permissions match this filter.')).toBeVisible();
  });

  test('keeps rows in registry order', () => {
    renderPage();

    const rendered = screen
      .getAllByText(/^users\./, { selector: 'code' })
      .map((node) => node.textContent);
    expect(rendered).toEqual(['users.delete', 'users.invite', 'users.read', 'users.write']);
  });
});
