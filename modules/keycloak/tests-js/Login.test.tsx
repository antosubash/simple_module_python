/**
 * The redirect interstitial nobody sees on a working install.
 *
 * `Keycloak/Login` calls `window.location.assign` from a mount effect, so in a
 * healthy install this card is painted for the length of one navigation. That
 * made its only evidence a pair of screenshots — and those were wrong: the
 * capture followed the redirect, so both files were byte-identical to
 * `07-keycloak-loggedout`, two screens claiming to be different and showing the
 * same one.
 *
 * The card still matters. It is what a visitor is left looking at when the
 * realm is unreachable or JavaScript is off, and its manual link is the only
 * way forward from there. So it gets a test rather than only a picture.
 */
import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

const REALM = 'https://sso.example.com/realms/acme';
const START_LOGIN_URL = '/api/keycloak/auth/login';

configureI18n({
  locale: 'en',
  messages: {
    'keycloak.login.title': 'Signing in',
    'keycloak.login.redirecting': 'Redirecting to your identity provider',
    'keycloak.login.body_prefix': 'Taking you to',
    'keycloak.login.body_suffix': ". You'll come straight back once signed in.",
    'keycloak.login.body_generic':
      "Taking you to your identity provider. You'll come straight back.",
    'keycloak.login.progress_label': 'Redirecting',
    'keycloak.login.manual': 'Not redirected? Continue manually',
  },
});

const assign = vi.fn();
let props: { realm_url: string } = { realm_url: REALM };

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  usePage: () => ({ props }),
}));

vi.stubGlobal('location', { assign } as unknown as Location);

import Login from '../keycloak/pages/Login';

beforeEach(() => {
  assign.mockClear();
  props = { realm_url: REALM };
});

describe('the redirect it fires', () => {
  test('it leaves for the realm on mount, which is why it is never read', () => {
    render(<Login />);
    expect(assign).toHaveBeenCalledWith(START_LOGIN_URL);
  });
});

describe('what is left on screen when the redirect does not happen', () => {
  test('it names the realm it is sending you to', () => {
    render(<Login />);

    expect(
      screen.getByRole('heading', { name: 'Redirecting to your identity provider' }),
    ).toBeInTheDocument();
    expect(screen.getByText(REALM)).toBeInTheDocument();
  });

  test('it says nothing it cannot vouch for when the realm is unset', () => {
    props = { realm_url: '' };
    render(<Login />);

    expect(screen.queryByText(REALM)).not.toBeInTheDocument();
    expect(
      screen.getByText("Taking you to your identity provider. You'll come straight back."),
    ).toBeInTheDocument();
  });

  test('the manual link is the way forward when the realm is unreachable', () => {
    render(<Login />);

    expect(screen.getByRole('link', { name: 'Not redirected? Continue manually' })).toHaveAttribute(
      'href',
      START_LOGIN_URL,
    );
  });

  test('the progress bar claims no progress it cannot observe', () => {
    render(<Login />);

    // Indeterminate: the wait is a navigation to another origin, whose progress
    // this page cannot see. ARIA reads a progressbar with no aria-valuenow as
    // indeterminate, which is exactly the claim being made.
    const bar = screen.getByRole('progressbar', { name: 'Redirecting' });
    expect(bar).not.toHaveAttribute('aria-valuenow');
  });
});
