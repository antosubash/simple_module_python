import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import de from '../oidc/locales/de.json';
import en from '../oidc/locales/en.json';
import LoggedOut from '../oidc/pages/LoggedOut';
import Login from '../oidc/pages/Login';

vi.mock('@inertiajs/react', () => ({
  Link: (props: React.AnchorHTMLAttributes<HTMLAnchorElement>) => <a {...props} />,
}));
vi.stubGlobal('location', { assign: vi.fn() });
afterEach(cleanup);

test('German login and signed-out pages use the supplied catalogue', () => {
  configureI18n({
    locale: 'de',
    messages: {
      'oidc.login.redirecting': de.login.redirecting,
      'oidc.login.manual': de.login.manual,
      'oidc.logout.title': de.logout.title,
      'oidc.logout.message': de.logout.message,
      'oidc.logout.sign_in_again': de.logout.sign_in_again,
    },
  });
  render(<Login />);
  expect(screen.getByRole('link', { name: de.login.manual })).toHaveAttribute(
    'href',
    '/api/oidc/auth/login',
  );
  render(<LoggedOut />);
  expect(screen.getByRole('heading', { name: de.logout.title })).toBeInTheDocument();
  expect(screen.getByText(de.logout.message)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: de.logout.sign_in_again })).toHaveAttribute(
    'href',
    '/oidc/login',
  );
});

test('English and German catalogues have matching keys', () => {
  for (const section of Object.keys(en) as (keyof typeof en)[]) {
    expect(Object.keys(de[section]).sort()).toEqual(Object.keys(en[section]).sort());
  }
});
