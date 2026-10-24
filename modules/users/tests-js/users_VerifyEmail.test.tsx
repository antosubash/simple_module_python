import { configureI18n, keys } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { json, stubFetch } from './users_fixtures';

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  usePage: () => ({ props: { branding: { appName: 'Acme', logoUrl: null } } }),
}));

import VerifyEmail from '../users/pages/VerifyEmail';

configureI18n({
  locale: 'en',
  messages: {
    [keys.users.common.error_try_again]: 'An error occurred. Please try again.',
    [keys.users.verify_email.expired_title]: 'Link expired',
    [keys.users.verify_email.already_title]: 'Already verified',
    [keys.users.verify_email.success_title]: 'Email verified',
    [keys.users.verify_email.incomplete_title]: 'Link incomplete',
  },
});

afterEach(() => vi.unstubAllGlobals());

function verify(token = 'verification-token') {
  render(<VerifyEmail token={token} email="user@example.com" verification_lifetime_days={3} />);
}

describe('VerifyEmail failure classification (#638)', () => {
  it.each([500, 429, 422, 403, 400])(
    'does not label HTTP %s as an expired link',
    async (status) => {
      stubFetch(() => json(status, { detail: 'Unexpected failure' }));
      verify();
      expect(await screen.findByText('An error occurred. Please try again.')).toBeInTheDocument();
      expect(screen.queryByText('Link expired')).toBeNull();
    },
  );

  it('does not label a network failure as an expired link', async () => {
    stubFetch(() => Promise.reject(new TypeError('Network unavailable')));
    verify();
    expect(await screen.findByText('An error occurred. Please try again.')).toBeInTheDocument();
    expect(screen.queryByText('Link expired')).toBeNull();
  });

  it.each([
    [400, 'VERIFY_USER_BAD_TOKEN', 'Link expired'],
    [400, 'VERIFY_USER_ALREADY_VERIFIED', 'Already verified'],
    [200, null, 'Email verified'],
    [204, null, 'Email verified'],
  ])('preserves the expected state for %s / %s', async (status, detail, title) => {
    stubFetch(() => (status === 204 ? new Response(null, { status }) : json(status, { detail })));
    verify();
    expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument();
  });

  it('shows an incomplete link without sending a request when the token is missing', () => {
    const fetch = stubFetch(() => json(500, null));
    verify('');
    expect(screen.getByRole('heading', { name: 'Link incomplete' })).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
});
