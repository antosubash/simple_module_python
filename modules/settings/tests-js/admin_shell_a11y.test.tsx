import { configureI18n } from '@simple-module-py/i18n';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import ModulesEdit from '../settings/pages/ModulesEdit';
import { FieldSource } from '../settings/ui/components/FieldSource';

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children, ...props }: React.ComponentProps<'a'>) => <a {...props}>{children}</a>,
  usePage: () => ({ url: '/admin/settings/', props: { menus: {}, auth: { user: null } } }),
}));

beforeEach(() => {
  configureI18n({
    locale: 'en',
    messages: {
      'ui.nav.sidebar': 'Section navigation',
      'ui.nav.footer': 'Footer links',
      'ui.nav.breadcrumb': 'Breadcrumb',
      'settings.modules.navigation_label': 'Settings modules',
      'settings.modules_form.revert_field': 'Revert {field}',
    },
  });
  vi.stubGlobal('matchMedia', () => ({
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  }));
});
afterEach(() => vi.unstubAllGlobals());

test('the settings screen has one main landmark inside the admin shell', () => {
  render(
    <AdminLayout>
      <ModulesEdit modules={[]} />
    </AdminLayout>,
  );
  expect(screen.getAllByRole('main')).toHaveLength(1);
});

test('each admin navigation landmark has a distinct translated label', () => {
  render(
    <AdminLayout>
      <ModulesEdit modules={[]} />
    </AdminLayout>,
  );
  const navs = screen.getAllByRole('navigation');
  expect(navs).toHaveLength(4);
  for (const label of ['Section navigation', 'Footer links', 'Breadcrumb', 'Settings modules']) {
    expect(screen.getByRole('navigation', { name: label })).toBeInTheDocument();
  }
});

test('a closed search dialog contributes no heading before the page heading', () => {
  render(
    <AdminLayout>
      <ModulesEdit modules={[]} />
    </AdminLayout>,
  );
  expect(screen.getAllByRole('heading')[0].tagName).toBe('H1');
});

test('each settings Revert button names the field it resets', () => {
  for (const name of ['smtp_host', 'sender']) {
    render(
      <FieldSource
        field={{
          name,
          db_override: true,
          type: 'string',
          value: '',
          default: '',
          description: '',
          is_secret: false,
          requires_restart: false,
          group: null,
          env_var: 'SM_TEST_SETTING',
        }}
        onReset={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: `Revert ${name}` })).toBeInTheDocument();
  }
});
