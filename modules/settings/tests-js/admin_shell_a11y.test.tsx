import { configureI18n } from '@simple-module-py/i18n';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import Browse from '../settings/pages/Browse';
import Edit from '../settings/pages/Edit';
import ModulesEdit from '../settings/pages/ModulesEdit';
import { FieldInput, type FieldMeta } from '../settings/ui/components/FieldInput';
import { FieldSource } from '../settings/ui/components/FieldSource';
import ValueInput from '../settings/ui/components/ValueInput';

vi.mock('@inertiajs/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@inertiajs/react')>()),
  Head: () => null,
  Link: ({ children, ...props }: React.ComponentProps<'a'>) => <a {...props}>{children}</a>,
  usePage: () => ({ url: '/admin/settings/', props: { menus: {}, auth: { user: null } } }),
  router: { on: () => () => {}, replace: vi.fn(), reload: vi.fn() },
}));

beforeEach(() => {
  configureI18n({
    locale: 'en',
    messages: {
      'ui.nav.sidebar': 'Section navigation',
      'ui.nav.footer': 'Footer links',
      'ui.nav.breadcrumb': 'Breadcrumb',
      'settings.modules.search_label': 'Search settings modules',
      'settings.browse.search_label': 'Search stored settings',
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

function renderSettingsScreen() {
  render(
    <AdminLayout>
      <ModulesEdit modules={[]} />
    </AdminLayout>,
  );
}

test('the settings screen has one main landmark inside the admin shell', () => {
  renderSettingsScreen();
  expect(screen.getAllByRole('main')).toHaveLength(1);
});

test('each admin navigation landmark has a distinct translated label', () => {
  renderSettingsScreen();
  const navs = screen.getAllByRole('navigation');
  expect(navs).toHaveLength(4);
  for (const label of ['Section navigation', 'Footer links', 'Breadcrumb', 'Settings modules']) {
    expect(screen.getByRole('navigation', { name: label })).toBeInTheDocument();
  }
});

test('a closed search dialog contributes no heading before the page heading', () => {
  renderSettingsScreen();
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

test('settings module search has a translated accessible name', () => {
  render(<ModulesEdit modules={[]} />);
  expect(screen.getByRole('searchbox', { name: 'Search settings modules' })).toBeInTheDocument();
});

test('settings store search has a translated accessible name', () => {
  render(
    <Browse
      settings={[]}
      pagination={{ page: 1, per_page: 20, total: 0 }}
      counts={{ all: 0, system: 0, tenant: 0, user: 0 }}
      filters={{ scope: 'all', q: '' }}
    />,
  );
  expect(screen.getByRole('searchbox', { name: 'Search stored settings' })).toBeInTheDocument();
});

test.each(['int', 'float'] as const)(
  'settings %s inputs reach 44px on narrow/coarse screens',
  (type) => {
    const field: FieldMeta = {
      name: 'count',
      type,
      value: 1,
      default: 1,
      description: '',
      is_secret: false,
      requires_restart: false,
      group: null,
      env_var: '',
    };
    render(
      <>
        <FieldInput field={field} value={1} onChange={() => {}} />
        <ValueInput valueType={type} value="1" onValueChange={() => {}} />
      </>,
    );
    for (const input of screen.getAllByRole('spinbutton')) {
      expect(input).toHaveClass('max-lg:min-h-11', 'pointer-coarse:min-h-11');
    }
  },
);

test('the settings store Save button reaches 44px on narrow/coarse screens', () => {
  render(
    <Edit
      setting={{
        id: 1,
        scope: 'system',
        scope_id: '',
        key: 'limit',
        value: '1',
        value_type: 'int',
        description: null,
      }}
    />,
  );
  expect(screen.getByRole('button', { name: 'settings.edit.submit_button' })).toHaveClass(
    'max-lg:min-h-11',
    'pointer-coarse:min-h-11',
  );
});
