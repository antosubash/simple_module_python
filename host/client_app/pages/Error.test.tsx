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
import type { ReactNode } from 'react';
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

const mocks = vi.hoisted(() => ({
  page: { url: '/', props: { auth: { user: null } } } as {
    url: string;
    props: Record<string, unknown>;
  },
}));

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children, ...rest }: { children?: unknown }) => <a {...rest}>{children as never}</a>,
  router: { visit: vi.fn(), reload: vi.fn() },
  // Only shared props come from the page here — the rest are ordinary
  // component props, which is what Inertia passes a page component.
  usePage: () => mocks.page,
}));

vi.mock('@simple-module-py/ui/layouts/AdminLayout', () => ({
  AdminLayout: ({ children }: { children?: ReactNode }) => (
    <div data-testid="admin-layout">{children}</div>
  ),
}));

const { default: ErrorPage } = await import('./Error');

function renderError(props: Record<string, unknown>) {
  const layout = (ErrorPage as unknown as { layout: (page: ReactNode) => ReactNode }).layout;
  render(<>{layout(<ErrorPage {...(props as never)} />)}</>);
}

function setPage(url: string, props: Record<string, unknown>) {
  mocks.page = { url, props };
}

const ADMIN_MENUS = { menus: { adminSidebar: [{ label: 'Users', url: '/admin/users/' }] } };

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

describe('an error under /admin', () => {
  test('renders inside AdminLayout for a signed-in admin', () => {
    setPage('/admin/users/999999', { auth: { isAuthenticated: true }, ...ADMIN_MENUS });
    renderError({ status: 404, message: '' });

    expect(screen.getByTestId('admin-layout')).toBeInTheDocument();
    expect(screen.getByText('That page is not here.')).toBeInTheDocument();
  });

  test('renders bare for an anonymous 401', () => {
    setPage('/admin/users/', { auth: { isAuthenticated: false }, ...ADMIN_MENUS });
    renderError({ status: 401, message: '' });

    expect(screen.queryByTestId('admin-layout')).not.toBeInTheDocument();
  });

  test('renders bare outside /admin, matching whole path segments', () => {
    setPage('/administer', { auth: { isAuthenticated: true }, ...ADMIN_MENUS });
    renderError({ status: 404, message: '' });

    expect(screen.queryByTestId('admin-layout')).not.toBeInTheDocument();
  });

  test('renders bare when the admin menu is empty', () => {
    setPage('/admin/users/', { auth: { isAuthenticated: true }, menus: { adminSidebar: [] } });
    renderError({ status: 403, message: '' });

    expect(screen.queryByTestId('admin-layout')).not.toBeInTheDocument();
  });

  test('renders bare, without throwing, when shared props never arrived', () => {
    setPage('/admin/users/', {});
    renderError({ status: 500, message: '' });

    expect(screen.queryByTestId('admin-layout')).not.toBeInTheDocument();
  });
});
