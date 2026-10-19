import { configureI18n, keys, updateI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  usePage: () => ({ props: { branding: { appName: 'Acme', logoUrl: null } } }),
}));

import Register from '../users/pages/Register';

const r = keys.users.register;
const note = r.bullet_close;
const verification = r.bullet_verification;
const messages = {
  [note]: 'Registration may be closed',
  [verification]: 'Verify your email',
  [r.bullet_no_verification]: 'Sign in right away',
  [r.success_title]: 'Check your inbox',
  [r.success_ready_title]: 'Account created',
};

// A host locale override is delivered as a new catalog on an Inertia visit.
configureI18n({ locale: 'en', messages });

afterEach(() => {
  act(() => updateI18n({ locale: 'en', messages }));
  vi.unstubAllGlobals();
});

describe('Register aside', () => {
  it('renders the full public-facing note without an internal setting name', () => {
    render(<Register />);
    expect(screen.getByText('Registration may be closed')).toBeInTheDocument();
    expect(screen.queryByText(/users\.allow_signup/)).toBeNull();
  });

  it('omits the entire check row when the host overrides the note to empty', () => {
    act(() => updateI18n({ locale: 'en', messages: { ...messages, [note]: '  ' } }));
    render(<Register />);
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByText('Verify your email')).toBeInTheDocument();
  });
});

function submitValidForm() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(null, { status: 201 })),
  );
  fireEvent.change(document.getElementById('email') as HTMLElement, {
    target: { value: 'new@example.com' },
  });
  const [password, confirm] = Array.from(document.querySelectorAll('input[type="password"]'));
  fireEvent.change(password, { target: { value: 'Str0ng-Passphrase' } });
  fireEvent.change(confirm, { target: { value: 'Str0ng-Passphrase' } });
  fireEvent.submit(document.querySelector('form') as HTMLFormElement);
}

describe('Register follows users.require_verification (#547)', () => {
  it('promises a verification email when verification is required', async () => {
    render(<Register require_verification />);
    expect(screen.getByText('Verify your email')).toBeInTheDocument();
    submitValidForm();
    await waitFor(() => expect(screen.getByText('Check your inbox')).toBeInTheDocument());
  });

  it('says the account is ready when verification is off', async () => {
    render(<Register require_verification={false} />);
    expect(screen.queryByText('Verify your email')).toBeNull();
    expect(screen.getByText('Sign in right away')).toBeInTheDocument();
    submitValidForm();
    await waitFor(() => expect(screen.getByText('Account created')).toBeInTheDocument());
    expect(screen.queryByText('Check your inbox')).toBeNull();
  });
});
