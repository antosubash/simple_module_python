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

import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
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

  it('puts the light split on two surfaces rather than one', () => {
    // Both columns used to be `bg-background`, which left the card's 1px
    // border as the only thing marking the split — the layout read as a single
    // surface with a box on it.
    render(
      <AuthCardShell variant="split-light" aside={<p>Create your account</p>} width="lg">
        <form aria-label="Register" />
      </AuthCardShell>,
    );

    const asideColumn = screen.getByText('Create your account').closest('[class*="bg-secondary/"]');
    expect(asideColumn).not.toBeNull();
    expect(asideColumn).not.toContainElement(screen.getByRole('form', { name: 'Register' }));
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
    expect(container.querySelector('[class*="border-border"]')).not.toBeNull();
  });

  it('tints the card border red for a destructive tone', () => {
    const { container } = render(
      <AuthCardShell tone="destructive">
        <form aria-label="Reset" />
      </AuthCardShell>,
    );
    expect(container.querySelector('[class*="border-red-500/35"]')).not.toBeNull();
  });

  it('tints the card border amber for a warning tone', () => {
    const { container } = render(
      <AuthCardShell tone="warning">
        <form aria-label="Verify" />
      </AuthCardShell>,
    );
    expect(container.querySelector('[class*="border-amber-600/35"]')).not.toBeNull();
  });
});

describe('AuthCardShell control sizing', () => {
  /** The deck's auth fields are 46px and its primary buttons 48px. */
  function expectDeckSizing(card: HTMLElement | null) {
    expect(card).toHaveClass('[&_[data-slot=input]]:h-[46px]');
    expect(card).toHaveClass('[&_[data-slot=button][data-size=lg]]:h-12');
    // The rules above only bite through the primitives' own hooks, so assert
    // those too: a shadcn re-vendor that drops them would silently un-size
    // every auth screen.
    expect(screen.getByRole('textbox', { name: 'Email' })).toHaveAttribute('data-slot', 'input');
    expect(screen.getByRole('button', { name: 'Sign in' })).toHaveAttribute('data-size', 'lg');
  }

  const form = (
    <form aria-label="Sign in">
      <Input aria-label="Email" />
      <Button size="lg">Sign in</Button>
    </form>
  );

  it('sizes the centred card’s controls to the deck', () => {
    render(<AuthCardShell>{form}</AuthCardShell>);
    expectDeckSizing(screen.getByRole('form', { name: 'Sign in' }).parentElement);
  });

  it('sizes the split card’s controls to the deck', () => {
    render(
      <AuthCardShell variant="split-dark" aside={<p>One admin surface</p>}>
        {form}
      </AuthCardShell>,
    );
    expectDeckSizing(screen.getByRole('form', { name: 'Sign in' }).parentElement);
  });
});
