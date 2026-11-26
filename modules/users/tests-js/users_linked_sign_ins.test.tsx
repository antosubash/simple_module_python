import '@testing-library/jest-dom/vitest';
import type { VisitOptions } from '@inertiajs/core';
import { configureI18n } from '@simple-module-py/i18n';
import { setCsrfToken } from '@simple-module-py/ui/lib/csrf-token';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

const { remove, reload, success, error } = vi.hoisted(() => ({
  remove: vi.fn(),
  reload: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock('@inertiajs/react', () => ({ router: { delete: remove, reload, on: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success, error } }));

configureI18n({
  locale: 'en',
  messages: {
    'users.linked_sign_ins.remove': 'Remove',
    'users.linked_sign_ins.confirm_title': 'Remove {provider} sign-in?',
    'users.linked_sign_ins.confirm_body': 'This identity will no longer sign in as this user.',
    'users.linked_sign_ins.last_link_warning':
      'This is the last linked sign-in, so the user will need a provider identity with a verified email address matching this account, or another sign-in method, to sign in again.',
    'users.linked_sign_ins.removed': 'Sign-in removed',
    'users.linked_sign_ins.remove_failed': 'Could not remove sign-in',
    'users.linked_sign_ins.duplicates': 'Multiple identities are linked for the same provider.',
    'users.common.cancel': 'Cancel',
    'users.linked_sign_ins.title': 'Linked sign-ins',
    'users.linked_sign_ins.subject': 'Subject',
    'users.linked_sign_ins.last_sign_in': 'Last signed in {when}',
    'users.linked_sign_ins.never': 'Not signed in through it yet',
  },
});

import { LinkedSignInsCard } from '../users/pages/Users/components/LinkedSignInsCard';

describe('LinkedSignInsCard', () => {
  test('lists each provider with its username, subject and last sign-in', () => {
    render(
      <LinkedSignInsCard
        userId="user-1"
        hasDuplicates={false}
        links={[
          {
            id: 'ms-1',
            provider: 'Microsoft',
            username: 'jane@corp.com',
            subject: 'pairwise-sub',
            last_sign_in_at: new Date().toISOString(),
          },
          { id: 'gh-1', provider: 'GitHub', username: null, subject: null, last_sign_in_at: null },
        ]}
      />,
    );
    expect(screen.getByText('Linked sign-ins')).toBeInTheDocument();
    expect(screen.getByText('Microsoft')).toBeInTheDocument();
    expect(screen.getByText(/jane@corp\.com/)).toBeInTheDocument();
    expect(screen.getByText('pairwise-sub')).toBeInTheDocument();
    expect(screen.getByText(/^Last signed in/)).toBeInTheDocument();
    expect(screen.getByText('Not signed in through it yet')).toBeInTheDocument();
  });
});

const links = [
  {
    id: 'link-1',
    provider: 'Microsoft',
    username: 'jane@corp.com',
    subject: 'sub',
    last_sign_in_at: null,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  setCsrfToken('session-token');
});

test('duplicate callout follows the server prop', () => {
  const { rerender } = render(
    <LinkedSignInsCard userId="user-1" links={links} hasDuplicates={true} />,
  );
  expect(screen.getByRole('alert')).toHaveTextContent(/Multiple identities/);
  rerender(<LinkedSignInsCard userId="user-1" links={links} hasDuplicates={false} />);
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test.each([1, 2])('last-link warning appears only with one link (%i links)', (count) => {
  render(
    <LinkedSignInsCard
      userId="user-1"
      links={[links[0], { ...links[0], id: 'link-2' }].slice(0, count)}
      hasDuplicates={false}
    />,
  );
  fireEvent.click(screen.getAllByRole('button', { name: 'Remove' })[0]);
  const dialog = screen.getByRole('alertdialog');
  expect(dialog).toHaveTextContent('This identity will no longer sign in as this user.');
  const warning = within(dialog).queryByText(/This is the last linked sign-in/);
  if (count === 1) {
    expect(warning).toHaveTextContent(/verified email address matching this account/);
    expect(warning).toHaveTextContent(/or another sign-in method/);
  } else {
    expect(warning).not.toBeInTheDocument();
  }
});

test('cancel keeps the link; confirm deletes its view URL and reports success', () => {
  render(<LinkedSignInsCard userId="user-1" links={links} hasDuplicates={false} />);
  fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
  expect(screen.getByRole('alertdialog')).toHaveTextContent('Remove Microsoft sign-in?');
  expect(remove).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(remove).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove' }));
  expect(remove).toHaveBeenCalledWith(
    '/admin/users/user-1/linked-sign-ins/link-1',
    expect.any(Object),
  );
  const options: Pick<VisitOptions, 'headers' | 'only'> & {
    onStart: () => void;
    onSuccess: () => void;
    onError: () => void;
    onHttpException: () => void;
    onNetworkError: () => void;
    onFinish: () => void;
  } = remove.mock.calls[0][1];
  expect(options.headers?.['X-CSRF-Token']).toBe('session-token');
  expect(options.only).toEqual(['linked_sign_ins', 'has_duplicate_linked_sign_ins']);
  act(() => {
    options.onStart();
  });
  expect(
    screen.getAllByRole('button', { name: 'Remove' }).every((b) => b.hasAttribute('disabled')),
  ).toBe(true);
  act(() => {
    options.onSuccess();
  });
  act(() => {
    options.onFinish();
  });
  expect(success).toHaveBeenCalledWith('Sign-in removed');
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
});

test.each([
  { failure: 'onError', status: undefined, reloads: false },
  { failure: 'onNetworkError', status: undefined, reloads: false },
  { failure: 'onHttpException', status: 403, reloads: false },
  { failure: 'onHttpException', status: 404, reloads: true },
] as const)(
  '$failure ($status) reports failed removal; refreshes the list only after a 404',
  async ({ failure, status, reloads }) => {
    render(<LinkedSignInsCard userId="user-1" links={links} hasDuplicates={false} />);
    const opener = screen.getByRole('button', { name: 'Remove' });
    fireEvent.click(opener);
    fireEvent.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove' }),
    );
    const options: Pick<VisitOptions, 'headers' | 'only'> & {
      onStart: () => void;
      onSuccess: () => void;
      onError: () => void;
      onHttpException: (response: { status: number }) => void;
      onNetworkError: () => void;
      onFinish: () => void;
    } = remove.mock.calls[0][1];
    act(() => {
      if (failure === 'onHttpException') options.onHttpException({ status: status ?? 500 });
      else options[failure]();
      options.onFinish();
    });
    expect(error).toHaveBeenCalledWith('Could not remove sign-in');
    expect(screen.getByRole('button', { name: 'Remove' })).toBeEnabled();
    if (reloads) {
      // The refresh must not let an error page replace the dirty form.
      expect(reload).toHaveBeenCalledWith(
        expect.objectContaining({ only: ['linked_sign_ins', 'has_duplicate_linked_sign_ins'] }),
      );
      expect(reload.mock.calls[0][0].onHttpException()).toBe(false);
    } else {
      expect(reload).not.toHaveBeenCalled();
    }
    await waitFor(() => expect(opener).toHaveFocus());
  },
);

test('each duplicate provider row removes its own link id', () => {
  render(
    <LinkedSignInsCard
      userId="user-1"
      hasDuplicates={true}
      links={[links[0], { ...links[0], id: 'link-2' }]}
    />,
  );
  fireEvent.click(screen.getAllByRole('button', { name: 'Remove' })[1]);
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove' }));
  expect(remove).toHaveBeenCalledWith(
    '/admin/users/user-1/linked-sign-ins/link-2',
    expect.any(Object),
  );
});

test.each(['Cancel', 'Escape'])(
  '%s returns focus to the Remove button that opened it',
  async (close) => {
    render(<LinkedSignInsCard userId="user-1" links={links} hasDuplicates={false} />);
    const opener = screen.getByRole('button', { name: 'Remove' });
    fireEvent.click(opener);
    if (close === 'Cancel') fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    else fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    await waitFor(() => expect(opener).toHaveFocus());
  },
);

test('a failure refresh that removes the stale row keeps focus in the card', async () => {
  const { rerender } = render(
    <LinkedSignInsCard userId="user-1" links={links} hasDuplicates={false} />,
  );
  const opener = screen.getByRole('button', { name: 'Remove' });
  fireEvent.click(opener);
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove' }));
  const options = remove.mock.calls[0][1];
  act(() => {
    options.onHttpException({ status: 404 });
    options.onFinish();
  });
  await waitFor(() => expect(opener).toHaveFocus());
  rerender(<LinkedSignInsCard userId="user-1" links={[]} hasDuplicates={false} />);
  await waitFor(() =>
    expect(screen.getByRole('heading', { name: 'Linked sign-ins' })).toHaveFocus(),
  );
});

test.each([
  { count: 3, index: 1, target: 'link-3' },
  { count: 2, index: 1, target: 'link-1' },
  { count: 1, index: 0, target: null },
])(
  'removing row $index of $count focuses $target or the heading',
  async ({ count, index, target }) => {
    const rows = Array.from({ length: count }, (_, i) => ({ ...links[0], id: `link-${i + 1}` }));
    const { rerender } = render(
      <LinkedSignInsCard userId="user-1" links={rows} hasDuplicates={false} />,
    );
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove' })[index]);
    fireEvent.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove' }),
    );
    const options = remove.mock.calls[0][1];
    act(() => options.onStart());
    const remaining = rows.filter((_, i) => i !== index);
    rerender(<LinkedSignInsCard userId="user-1" links={remaining} hasDuplicates={false} />);
    act(() => {
      options.onSuccess();
      options.onFinish();
    });
    const expected = target
      ? screen.getAllByRole('button', { name: 'Remove' })[
          remaining.findIndex((r) => r.id === target)
        ]
      : screen.getByRole('heading', { name: 'Linked sign-ins' });
    await waitFor(() => expect(expected).toHaveFocus());
  },
);
