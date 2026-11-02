import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { json, sent, stubFetch } from './users_fixtures';

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  router: { visit: vi.fn() },
  usePage: () => ({ props: { branding: { appName: 'Acme', logoUrl: null } } }),
}));

import ResetPassword from '../users/pages/ResetPassword';

configureI18n({
  locale: 'en',
  messages: {
    [keys.users.common.error_try_again]: 'Please try again.',
    [keys.users.reset_password.error_failed]: 'The reset link may have expired.',
    [keys.users.reset_password.saved_title]: 'Password saved',
    [keys.users.reset_password.submit]: 'Save password',
  },
});

afterEach(() => vi.unstubAllGlobals());

function reset() {
  render(
    <ResetPassword
      token="same-token"
      email={null}
      expired={false}
      reset_link_lifetime_minutes={60}
    />,
  );
}

function submit(password: string) {
  for (const id of ['password', 'confirm']) {
    fireEvent.change(document.getElementById(id) as HTMLElement, { target: { value: password } });
  }
  fireEvent.submit(document.querySelector('form') as HTMLFormElement);
}

describe('ResetPassword password policy errors (#667)', () => {
  it.each([
    ['short', 'Password must be at least 8 characters, not counting spaces'],
    ['12345678', 'Password cannot be all numbers'],
  ])('shows the policy reason for %s and retries with the same token', async (weak, reason) => {
    const fetch = stubFetch(() =>
      json(400, { detail: { code: 'RESET_PASSWORD_INVALID_PASSWORD', reason } }),
    );
    reset();
    submit(weak);
    expect(await screen.findByText(reason)).toBeInTheDocument();
    expect(screen.queryByText('The reset link may have expired.')).toBeNull();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save password' })).toBeEnabled(),
    );
    fetch.mockImplementation(async () => json(200, null));
    submit('CompliantPass1!');
    expect(await screen.findByRole('heading', { name: 'Password saved' })).toBeInTheDocument();
    expect(screen.queryByText(reason)).toBeNull();
    expect(JSON.parse((await sent(fetch, 0)).text)).toEqual({
      token: 'same-token',
      password: weak,
    });
    expect(JSON.parse((await sent(fetch, 1)).text)).toEqual({
      token: 'same-token',
      password: 'CompliantPass1!',
    });
  });

  it.each([
    null,
    { code: 'UNRELATED', reason: 'Do not display' },
    { code: 'RESET_PASSWORD_INVALID_PASSWORD', reason: 42 },
    { code: 'RESET_PASSWORD_INVALID_PASSWORD', reason: '' },
    { code: 'RESET_PASSWORD_INVALID_PASSWORD', reason: '   ' },
    ['RESET_PASSWORD_INVALID_PASSWORD'],
  ])('falls back safely for malformed or unrelated detail %j', async (detail) => {
    stubFetch(() => json(400, { detail }));
    reset();
    submit('short');
    expect(await screen.findByText('The reset link may have expired.')).toBeInTheDocument();
    expect(screen.queryByText('Do not display')).toBeNull();
  });

  it('does not treat a server failure as a password policy rejection', async () => {
    stubFetch(() =>
      json(500, {
        detail: { code: 'RESET_PASSWORD_INVALID_PASSWORD', reason: 'Do not display' },
      }),
    );
    reset();
    submit('short');
    expect(await screen.findByText('The reset link may have expired.')).toBeInTheDocument();
    expect(screen.queryByText('Do not display')).toBeNull();
  });

  it('preserves bad-token details', async () => {
    stubFetch(() => json(400, { detail: 'RESET_PASSWORD_BAD_TOKEN' }));
    reset();
    submit('CompliantPass1!');
    expect(await screen.findByText('RESET_PASSWORD_BAD_TOKEN')).toBeInTheDocument();
  });

  it('keeps network failures separate from expired links', async () => {
    stubFetch(() => Promise.reject(new TypeError('Offline')));
    reset();
    submit('CompliantPass1!');
    expect(await screen.findByText('Please try again.')).toBeInTheDocument();
    expect(screen.queryByText('The reset link may have expired.')).toBeNull();
  });
});
