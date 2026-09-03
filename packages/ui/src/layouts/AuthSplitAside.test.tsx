import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@inertiajs/react', () => ({
  usePage: () => ({ props: { branding: { appName: 'Acme', logoUrl: null, logoDarkUrl: null } } }),
}));

import { AuthSplitAside } from './AuthSplitAside';

describe('AuthSplitAside', () => {
  it('renders the lockup, the pitch, every check and the copyright', () => {
    render(
      <AuthSplitAside
        heading="One admin surface for every module you install."
        body="Users, permissions, settings, files."
        checks={['Sessions, invites and password reset built in', 'Keycloak SSO when you need it']}
      />,
    );
    expect(screen.getAllByText('Acme').length).toBeGreaterThan(0);
    expect(
      screen.getByRole('heading', { name: 'One admin surface for every module you install.' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Users, permissions, settings, files.')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByText(new RegExp(`© ${new Date().getFullYear()} Acme`))).toBeInTheDocument();
  });
});
