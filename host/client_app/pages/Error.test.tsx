/**
 * The 403 branch that names the missing permission.
 *
 * `Error.tsx` had no test, and its most interesting line is the one that
 * splices a `<code>`-wrapped permission name into a translated sentence. That
 * is the wording which tells a reader *what to go and ask for* — the fallback
 * only says "your role doesn't include the permission this page needs", which
 * they cannot act on.
 *
 * Three sources feed the description, most specific first, and the precedence
 * between them is what this pins.
 */
import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'host.error.forbidden_title': 'No access',
    'host.error.forbidden_description':
      "Your role doesn't include the permission this page needs. Ask an admin to grant it.",
    'host.error.forbidden_permission':
      "Your role doesn't include {permission}. Ask an admin to grant it.",
    'host.error.not_found_title': 'Not found',
    'host.error.not_found_description': 'That page is not here.',
    'host.error.go_home': 'Go home',
    'host.error.sign_in': 'Sign in',
    'host.error.retry': 'Retry',
    'host.error.server_title': 'Something broke',
    'host.error.server_description': 'Something went wrong on our side.',
    'host.error.unauthorized_title': 'Sign in to continue',
    'host.error.unauthorized_description': 'You need to be signed in.',
    'host.error.maintenance_title': 'Back shortly',
    'host.error.maintenance_description': 'Planned maintenance.',
    'host.error.correlation_label': 'Reference',
  },
});

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children, ...rest }: { children?: unknown }) => <a {...rest}>{children as never}</a>,
  router: { visit: vi.fn(), reload: vi.fn() },
  // Only `auth` comes from the page props here — the rest are ordinary
  // component props, which is what Inertia passes a page component.
  usePage: () => ({ props: { auth: { user: null } } }),
}));

const { default: ErrorPage } = await import('./Error');

function renderError(props: Record<string, unknown>) {
  render(<ErrorPage {...(props as never)} />);
}

describe('a 403 from a permission guard', () => {
  test('it names the permission, so the reader knows what to ask for', () => {
    renderError({ status: 403, message: '', required_permission: 'settings.manage' });

    expect(screen.getByText('settings.manage')).toBeInTheDocument();
    // The name is spliced into the sentence, not appended to it.
    expect(
      screen.getByText(/Your role doesn't include/).textContent?.replace(/\s+/g, ' '),
    ).toContain("Your role doesn't include settings.manage.");
  });

  test('the permission is rendered as code, not as prose', () => {
    renderError({ status: 403, message: '', required_permission: 'settings.manage' });

    expect(screen.getByText('settings.manage').tagName).toBe('CODE');
  });

  test('it beats a server-supplied message', () => {
    // The server's message for this case is the guard's log sentence
    // ("Permission required: settings.manage"), not copy for a human.
    renderError({
      status: 403,
      message: 'Permission required: settings.manage',
      required_permission: 'settings.manage',
    });

    expect(screen.queryByText(/^Permission required:/)).not.toBeInTheDocument();
  });
});

describe('a 403 with no single permission to name', () => {
  test('it falls back to the canned description', () => {
    // Role-gated and hand-raised 403s send `required_permission: null`.
    renderError({ status: 403, message: '', required_permission: null });

    expect(
      screen.getByText(
        "Your role doesn't include the permission this page needs. Ask an admin to grant it.",
      ),
    ).toBeInTheDocument();
  });

  test('a server message wins over the canned description', () => {
    renderError({
      status: 403,
      message: 'This workspace is read-only.',
      required_permission: null,
    });

    expect(screen.getByText('This workspace is read-only.')).toBeInTheDocument();
  });
});
