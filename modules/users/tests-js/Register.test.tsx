import { configureI18n, keys, updateI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { act } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const pageProps = vi.hoisted(() => ({}) as Record<string, unknown>);

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  usePage: () => ({ props: { branding: { appName: 'Acme', logoUrl: null }, ...pageProps } }),
}));

import Register from '../users/pages/Register';

const note = keys.users.register.bullet_close;
const verification = keys.users.register.bullet_verification;

// A host locale override is delivered as a new catalog on an Inertia visit.
configureI18n({
  locale: 'en',
  messages: { [note]: 'Registration may be closed', [verification]: 'Verify your email' },
});

afterEach(() => {
  delete pageProps.require_verification;
  act(() => updateI18n({ locale: 'en', messages: { [note]: 'Registration may be closed' } }));
});

describe('Register aside', () => {
  it('renders the full public-facing note without an internal setting name', () => {
    render(<Register />);
    expect(screen.getByText('Registration may be closed')).toBeInTheDocument();
    expect(screen.queryByText(/users\.allow_signup/)).toBeNull();
  });

  it('omits the entire check row when the host overrides the note to empty', () => {
    act(() => updateI18n({ locale: 'en', messages: { [note]: '  ' } }));
    render(<Register />);
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByText('Verify your email')).toBeInTheDocument();
  });

  it('shows the verification notice when verification is required', () => {
    pageProps.require_verification = true;
    render(<Register />);
    expect(screen.getByText('Verify your email')).toBeInTheDocument();
  });

  it('omits the verification notice when verification is not required', () => {
    pageProps.require_verification = false;
    render(<Register />);
    expect(screen.queryByText('Verify your email')).toBeNull();
    expect(screen.getByText('Registration may be closed')).toBeInTheDocument();
  });
});
