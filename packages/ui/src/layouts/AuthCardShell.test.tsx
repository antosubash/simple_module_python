import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@inertiajs/react', () => ({
  usePage: () => ({ props: { branding: { appName: 'Acme', logoUrl: null, banner: null } } }),
  Head: () => null,
}));

vi.mock('@simple-module-py/i18n', () => ({
  useT: () => ({ t: (key: string) => key }),
  keys: { ui: {} },
}));

import { AuthCardShell } from './AuthCardShell';

describe('AuthCardShell', () => {
  it('renders the aside beside the card in the dark split', () => {
    const { container } = render(
      <AuthCardShell variant="split-dark" aside={<p>One admin surface</p>}>
        <form aria-label="Sign in" />
      </AuthCardShell>,
    );
    expect(screen.getByText('One admin surface')).toBeInTheDocument();
    expect(screen.getByRole('form', { name: 'Sign in' })).toBeInTheDocument();
    expect(container.querySelector('.bg-landing-bg')).not.toBeNull();
  });

  it('renders the aside on a light column in the light split', () => {
    const { container } = render(
      <AuthCardShell variant="split-light" aside={<p>Create your account</p>} width="lg">
        <form aria-label="Register" />
      </AuthCardShell>,
    );
    expect(screen.getByText('Create your account')).toBeInTheDocument();
    expect(container.querySelector('.bg-landing-bg')).toBeNull();
    expect(container.querySelector('.max-w-lg')).not.toBeNull();
  });

  it('keeps the centred card as the default, brand lockup included', () => {
    const { container } = render(
      <AuthCardShell>
        <form aria-label="Reset" />
      </AuthCardShell>,
    );
    expect(screen.getByText('Acme')).toBeInTheDocument();
    expect(container.querySelector('.bg-landing-bg')).toBeNull();
  });
});
