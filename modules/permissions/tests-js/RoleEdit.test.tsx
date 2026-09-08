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
    'permissions.edit.title': 'Edit role: {role}',
    'permissions.edit.head_title': 'Edit Role',
    'permissions.edit.empty': 'No permissions have been registered by any installed module.',
    'permissions.edit.no_matches': 'No permissions match this filter.',
    'permissions.edit.submit_button': 'Save role',
    'permissions.edit.reset_button': 'Reset',
    'permissions.edit.cancel_link': 'Cancel',
    'permissions.edit.filter_placeholder': 'Filter modules or permissions…',
    'permissions.edit.granted_only': 'Granted only',
    'permissions.edit.granted_summary': '{granted} of {total} granted',
    'permissions.edit.toggle_group_label': 'Toggle every {group} permission',
  },
});

const mocks = vi.hoisted(() => ({ put: vi.fn() }));

// A working `useForm`: these tests are about what the page does as its data
// changes, so a stub that never re-renders would assert nothing.
vi.mock('@inertiajs/react', async () => {
  const { useState } = await import('react');
  const sorted = (value: unknown) => JSON.stringify([...(value as string[])].sort());
  return {
    Head: () => null,
    Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
      <a href={href}>{children}</a>
    ),
    router: { on: () => () => {} },
    usePage: () => ({ url: '/admin/permissions/roles/r1/edit', props: {} }),
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

import RoleEdit from '../permissions/pages/RoleEdit';

const GROUPS = [
  { name: 'Users', permissions: ['users.delete', 'users.invite', 'users.read', 'users.write'] },
  { name: 'Files', permissions: ['file_storage.delete', 'file_storage.upload'] },
  { name: 'Settings', permissions: ['settings.manage', 'settings.read'] },
];

function renderPage() {
  return render(
    <RoleEdit
      role={{
        id: 'r1',
        name: 'editor',
        description: 'Can manage content and invite people, but not change system settings.',
      }}
      assigned={['users.read', 'users.write', 'file_storage.upload']}
      groups={GROUPS}
    />,
  );
}

const keyRow = (permissionKey: string) =>
  screen.getByText(permissionKey, { selector: 'code' }).closest('label') as HTMLElement;

const filterBox = () => screen.getByPlaceholderText('Filter modules or permissions…');

describe('RoleEdit', () => {
  test('renders the deck header, actions and granted summary', () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Edit role: editor' })).toBeVisible();
    expect(
      screen.getByText('Can manage content and invite people, but not change system settings.'),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Save role' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Cancel' })).toHaveAttribute('href', '/admin/users/');
    // The count is emphasised on its own, the way the deck bolds it.
    expect(screen.getByText('3', { selector: 'b' })).toBeVisible();
    expect(screen.getByText('of 8 granted')).toBeVisible();
  });

  test('names each module by its registry name, tagging the key prefix only when it differs', () => {
    renderPage();

    // The name is a heading, not decoration: cards are how this page is
    // structured, and the slug tag rides along inside it.
    expect(screen.getByRole('heading', { name: 'Files file_storage' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Users' })).toBeVisible();
    expect(screen.getByText('Files')).toBeVisible();
    expect(screen.getByText('file_storage')).toBeVisible();
    expect(screen.getByText('Users')).toBeVisible();
    expect(screen.queryByText('users', { selector: 'code' })).not.toBeInTheDocument();
  });

  test('shows a group count with spaces around the slash', () => {
    renderPage();

    expect(screen.getByText('2 / 4')).toBeVisible();
    expect(screen.getByText('1 / 2')).toBeVisible();
    expect(screen.getByText('0 / 2')).toBeVisible();
  });

  test('filters by permission key, keeping only the matching rows', () => {
    renderPage();

    fireEvent.change(filterBox(), { target: { value: 'invite' } });

    expect(screen.getByText('users.invite', { selector: 'code' })).toBeVisible();
    expect(screen.queryByText('users.read', { selector: 'code' })).not.toBeInTheDocument();
    expect(screen.queryByText('Files')).not.toBeInTheDocument();
    expect(screen.queryByText('Settings')).not.toBeInTheDocument();
  });

  test('filters by module name and by the key prefix, keeping every row of the module', () => {
    renderPage();

    fireEvent.change(filterBox(), { target: { value: 'files' } });
    expect(screen.getByText('file_storage.upload', { selector: 'code' })).toBeVisible();
    expect(screen.getByText('file_storage.delete', { selector: 'code' })).toBeVisible();
    expect(screen.queryByText('users.read', { selector: 'code' })).not.toBeInTheDocument();

    fireEvent.change(filterBox(), { target: { value: 'file_storage' } });
    expect(screen.getByText('file_storage.upload', { selector: 'code' })).toBeVisible();
  });

  test('distinguishes "nothing matched" from "nothing registered"', () => {
    const { unmount } = renderPage();

    fireEvent.change(filterBox(), { target: { value: 'nothing-matches-this' } });
    expect(screen.getByText('No permissions match this filter.')).toBeVisible();
    unmount();

    render(
      <RoleEdit role={{ id: 'r1', name: 'editor', description: null }} assigned={[]} groups={[]} />,
    );
    expect(
      screen.getByText('No permissions have been registered by any installed module.'),
    ).toBeVisible();
  });

  test('"Granted only" hides ungranted rows and modules with nothing granted', () => {
    renderPage();

    fireEvent.click(screen.getByRole('button', { name: 'Granted only' }));

    expect(screen.getByText('users.read', { selector: 'code' })).toBeVisible();
    expect(screen.getByText('users.write', { selector: 'code' })).toBeVisible();
    expect(screen.queryByText('users.delete', { selector: 'code' })).not.toBeInTheDocument();
    expect(screen.queryByText('Settings')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Granted only' }));
    expect(screen.getByText('users.delete', { selector: 'code' })).toBeVisible();
  });

  test('the module checkbox is tri-state and grants the whole module', () => {
    renderPage();

    const partial = screen.getByRole('checkbox', { name: 'Toggle every Users permission' });
    expect(partial).toHaveAttribute('data-state', 'indeterminate');
    // A partial module draws a dash over the vendored checkbox's tick: two
    // glyphs in the control, one of them hidden by class.
    expect(partial.parentElement?.querySelectorAll('svg')).toHaveLength(2);
    expect(
      screen.getByRole('checkbox', { name: 'Toggle every Settings permission' }),
    ).toHaveAttribute('data-state', 'unchecked');

    fireEvent.click(partial);

    expect(screen.getByText('4 / 4')).toBeVisible();
    expect(screen.getByRole('checkbox', { name: 'Toggle every Users permission' })).toHaveAttribute(
      'data-state',
      'checked',
    );
    expect(screen.getByText('of 8 granted')).toBeVisible();
    expect(screen.getByText('5', { selector: 'b' })).toBeVisible();
    const checked = screen.getByRole('checkbox', { name: 'Toggle every Users permission' });
    expect(checked.parentElement?.querySelectorAll('svg')).toHaveLength(1);
  });

  test('a row switch grants a single key and mutes the key while it is off', () => {
    renderPage();

    const off = within(keyRow('users.delete')).getByRole('switch');
    expect(off).toHaveAttribute('data-state', 'unchecked');
    expect(screen.getByText('users.delete', { selector: 'code' })).toHaveClass(
      'text-muted-foreground',
    );

    fireEvent.click(off);

    expect(within(keyRow('users.delete')).getByRole('switch')).toHaveAttribute(
      'data-state',
      'checked',
    );
    expect(screen.getByText('users.delete', { selector: 'code' })).not.toHaveClass(
      'text-muted-foreground',
    );
  });

  test('Save and Reset are gated on unsaved changes', () => {
    renderPage();

    expect(screen.getByRole('button', { name: 'Save role' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reset' })).toBeDisabled();

    fireEvent.click(within(keyRow('users.delete')).getByRole('switch'));

    expect(screen.getByRole('button', { name: 'Save role' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    expect(screen.getByRole('button', { name: 'Save role' })).toBeDisabled();
  });

  test('drops the footer badge the deck does not have', () => {
    renderPage();

    expect(screen.queryByText(/permissions enabled/)).not.toBeInTheDocument();
  });
});
