import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'oidc.login.redirecting': 'Redirecting to identity provider…',
    'oidc.login.title': 'Sign In',
  },
});
const assign = vi.fn();
vi.stubGlobal('location', { assign });

import Login from '../oidc/pages/Login';

test('login leaves the Inertia transport and provides a manual navigation link', () => {
  render(<Login />);
  expect(assign).toHaveBeenCalledWith('/api/oidc/auth/login');
  expect(screen.getByRole('link', { name: 'Sign In' })).toHaveAttribute(
    'href',
    '/api/oidc/auth/login',
  );
});
