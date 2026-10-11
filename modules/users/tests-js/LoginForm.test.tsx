import '@testing-library/jest-dom/vitest';
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
  test('announces a sign-in error as an alert', () => {
    render(<LoginForm {...baseProps} error="Invalid credentials" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid credentials');
  });

  test('renders no alert without an error', () => {
    render(<LoginForm {...baseProps} error={null} />);
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
