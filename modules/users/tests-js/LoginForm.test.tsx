import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

import { LoginForm } from '../users/auth_local/components/LoginForm';

const baseProps = {
  email: '',
  onEmailChange: vi.fn(),
  password: '',
  onPasswordChange: vi.fn(),
  remember: false,
  onRememberChange: vi.fn(),
  rememberDays: 30,
  loading: false,
  onSubmit: vi.fn(),
  allowSignup: false,
  oauthProviders: [],
};

describe('LoginForm', () => {
  test('falls back to the display name when a custom provider translation is missing', () => {
    configureI18n({
      locale: 'en',
      messages: { [keys.users.login.continue_with]: 'Continue with {name}' },
    });
    render(
      <LoginForm
        {...baseProps}
        error={null}
        oauthProviders={[
          { name: 'custom', display_name: 'Staff SSO', label_key: 'custom.login.missing' },
        ]}
      />,
    );
    expect(screen.getByRole('link', { name: 'Continue with Staff SSO' })).toHaveAttribute(
      'href',
      '/api/users/auth/custom/login',
    );
    configureI18n({ locale: 'en', messages: {} });
  });

  test('translates custom provider labels and keeps the registered login URL', () => {
    configureI18n({
      locale: 'en',
      messages: {
        'custom.login.sso': 'Staff SSO',
        [keys.users.login.continue_with]: 'Continue with {name}',
      },
    });
    const { rerender } = render(
      <LoginForm
        {...baseProps}
        error={null}
        oauthProviders={[
          { name: 'custom', display_name: 'Fallback', label_key: 'custom.login.sso', icon: 'key' },
          { name: 'github', display_name: 'GitHub' },
        ]}
      />,
    );
    const custom = screen.getByRole('link', { name: 'Continue with Staff SSO' });
    expect(custom).toHaveAttribute('href', '/api/users/auth/custom/login');
    expect(custom.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByRole('link', { name: 'Continue with GitHub' })).toHaveAttribute(
      'href',
      '/api/users/auth/github/login',
    );
    rerender(<LoginForm {...baseProps} error={null} oauthProviders={[]} />);
    expect(screen.queryByRole('link', { name: 'Continue with Staff SSO' })).toBeNull();
    configureI18n({ locale: 'en', messages: {} });
  });

  test('announces a sign-in error as an alert', () => {
    render(<LoginForm {...baseProps} error="Invalid credentials" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid credentials');
  });

  test('spaces the email, password and remember-me rows like the register form', () => {
    const { container } = render(<LoginForm {...baseProps} error={null} />);
    expect(container.querySelector('form')).toHaveClass('space-y-4');
    expect(container.querySelector('#remember')?.parentElement).toHaveClass('pt-1');
  });

  test('renders no alert without an error', () => {
    render(<LoginForm {...baseProps} error={null} />);
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
