import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const visit = vi.hoisted(() => vi.fn());
vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { visit },
  usePage: () => ({ props: { branding: { appName: 'Acme', logoUrl: null } } }),
}));

import { setCsrfToken } from '@simple-module-py/ui/lib/api';
import Login from '../users/pages/Login';
import { json, sent, stubFetch } from './users_fixtures';

configureI18n({ locale: 'en', messages: {} });

const props = {
  allow_signup: false,
  demo_signin: { accounts: [], read_only: false },
  login_redirect_url: '/dashboard',
  oauth_providers: [],
  remember_me_days: 30,
};

function submit() {
  fireEvent.change(document.querySelector('input[type="email"]') as HTMLElement, {
    target: { value: 'a@example.com' },
  });
  fireEvent.change(document.querySelector('input[type="password"]') as HTMLElement, {
    target: { value: 'secret-pw' },
  });
  fireEvent.submit(document.querySelector('form') as HTMLFormElement);
}

afterEach(() => {
  setCsrfToken(undefined);
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('users Login', () => {
  it.each([undefined, []])('renders the form without dev buttons for %s accounts', (accounts) => {
    render(<Login {...props} dev_accounts={accounts} />);
    expect(document.querySelector('input[type="email"]')).toBeInTheDocument();
    expect(document.querySelector('input[type="password"]')).toBeInTheDocument();
    expect(screen.queryByText(keys.users.login.dev_divider)).toBeNull();
  });

  it('fills credentials only when a dev account button is present and clicked', () => {
    render(
      <Login
        {...props}
        dev_accounts={[{ label: 'Admin', email: 'admin@example.com', password: 'AdminPass1!' }]}
      />,
    );
    expect(screen.getByText(keys.users.login.dev_divider)).toBeInTheDocument();
    expect(document.querySelector('input[type="email"]')).toHaveValue('');
    expect(document.querySelector('input[type="password"]')).toHaveValue('');
    fireEvent.click(screen.getByRole('button', { name: 'Admin' }));
    expect(document.querySelector('input[type="email"]')).toHaveValue('admin@example.com');
    expect(document.querySelector('input[type="password"]')).toHaveValue('AdminPass1!');
  });

  it.each([
    ['account_not_verified', keys.users.login.oauth_account_not_verified],
    ['signup_disabled', keys.users.login.oauth_signup_disabled],
    ['signin_failed', keys.users.login.oauth_signin_failed],
  ])('shows the translated OAuth message for %s', (code, key) => {
    configureI18n({ locale: 'en', messages: { [key]: 'Sign-in was refused.' } });
    render(<Login {...props} oauth_error={code} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Sign-in was refused.');
    configureI18n({ locale: 'en', messages: {} });
  });

  it('ignores unknown OAuth codes instead of displaying query text', () => {
    render(<Login {...props} oauth_error="<script>untrusted text</script>" />);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('posts the form-encoded credentials and follows the server redirect on 204', async () => {
    setCsrfToken('anonymous-session-token');
    const mock = stubFetch(() => new Response(null, { status: 204 }));
    render(<Login {...props} />);
    submit();
    await waitFor(() => expect(visit).toHaveBeenCalledWith('/dashboard'));
    const call = await sent(mock);
    expect(call.path).toBe('/api/users/auth/login');
    expect(call.method).toBe('POST');
    expect(call.csrf).toBe('anonymous-session-token');
    expect(call.contentType).toContain('application/x-www-form-urlencoded');
    expect(call.credentials).toBe('same-origin');
    const form = new URLSearchParams(call.text);
    expect(form.get('username')).toBe('a@example.com');
    expect(form.get('password')).toBe('secret-pw');
    expect(form.get('remember')).toBe('false');
  });

  it('shows the rate-limit copy on 429', async () => {
    stubFetch(() => json(429, { detail: 'slow down' }));
    render(<Login {...props} />);
    submit();
    expect(await screen.findByText(keys.users.login.error_rate_limited)).toBeInTheDocument();
    expect(visit).not.toHaveBeenCalled();
  });

  it('shows invalid credentials on any other failure', async () => {
    stubFetch(() => json(400, { detail: 'LOGIN_BAD_CREDENTIALS' }));
    render(<Login {...props} />);
    submit();
    expect(await screen.findByText(keys.users.login.error_invalid_credentials)).toBeInTheDocument();
  });

  it('says to try again when the request never reaches the server', async () => {
    stubFetch(() => {
      throw new TypeError('offline');
    });
    render(<Login {...props} />);
    submit();
    expect(await screen.findByText(keys.users.common.error_try_again)).toBeInTheDocument();
  });

  it('offers verification when the account is unverified', async () => {
    stubFetch(() => json(400, { detail: 'LOGIN_USER_NOT_VERIFIED' }));
    render(<Login {...props} />);
    submit();
    await waitFor(() =>
      expect(screen.queryByText(keys.users.login.error_invalid_credentials)).toBeNull(),
    );
    expect(document.querySelector('input[type="password"]')).toBeNull();
  });
});
