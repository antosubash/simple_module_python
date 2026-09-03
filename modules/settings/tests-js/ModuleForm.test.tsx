import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'settings.modules_form.saved_toast': 'Settings saved',
    'settings.modules_form.save': 'Save',
    'settings.modules_form.reset_to_default': 'Revert',
    'settings.modules_form.set_new_value': 'Set new value',
    'settings.modules.heading_suffix': 'settings',
    'settings.modules.description': 'Generated from the module’s declared settings.',
    'settings.modules.source_db': 'overridden in DB',
    'settings.modules.source_db_over_env': 'overridden in DB · shadows env',
    'settings.modules.secret_write_only': 'write-only · never returned',
    'settings.modules.unsaved_count_one': '{count} unsaved',
    'settings.modules.unsaved_count_other': '{count} unsaved',
    'settings.modules.test_connection': 'Test {name} connection',
    'settings.modules.test_connection_generic': 'Test connection',
  },
});

const mocks = vi.hoisted(() => ({ reload: vi.fn() }));

vi.mock('@inertiajs/react', () => ({
  router: { reload: mocks.reload },
}));

import type { FieldMeta } from '../settings/pages/components/FieldInput';
import { ModuleForm, type ModuleView } from '../settings/pages/components/ModuleForm';

function field(overrides: Partial<FieldMeta> & { name: string }): FieldMeta {
  return {
    type: 'string',
    value: '',
    default: '',
    description: '',
    is_secret: false,
    requires_restart: false,
    group: null,
    env_var: `SM_USERS_${overrides.name.toUpperCase()}`,
    env_set: false,
    env_readable: false,
    db_override: false,
    choices: null,
    ...overrides,
  };
}

function moduleView(fields: FieldMeta[]): ModuleView {
  return {
    module_name: 'Users',
    package: 'users',
    env_prefix: 'SM_USERS_',
    class_name: 'UsersSettings',
    fields,
  };
}

const retentionDays = field({ name: 'retention_days', type: 'int', value: 14, default: 14 });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  window.sessionStorage.clear();
});

describe('ModuleForm', () => {
  test('shows success feedback after settings are saved', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal('fetch', fetchMock);
    render(<ModuleForm module={moduleView([retentionDays])} />);

    fireEvent.change(screen.getByLabelText('retention_days'), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(screen.getByRole('status')).toBeVisible());
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/settings/modules/users',
      expect.objectContaining({ body: JSON.stringify({ retention_days: 30 }) }),
    );
    expect(mocks.reload).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent('Settings saved');
  });

  test('counts the dirty fields in the header', () => {
    render(
      <ModuleForm
        module={moduleView([retentionDays, field({ name: 'smtp_host', value: 'localhost' })])}
      />,
    );

    expect(screen.queryByText('1 unsaved')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('retention_days'), { target: { value: '30' } });
    expect(screen.getByText('1 unsaved')).toBeVisible();

    fireEvent.change(screen.getByLabelText('smtp_host'), { target: { value: 'mail.test' } });
    expect(screen.getByText('2 unsaved')).toBeVisible();
  });
});

describe('Revert', () => {
  test('is offered for a field a stored override supplies', () => {
    render(
      <ModuleForm
        module={moduleView([
          field({ name: 'smtp_host', value: 'mail.example.com', db_override: true }),
        ])}
      />,
    );

    expect(screen.getByText('overridden in DB')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Revert' })).toBeVisible();
  });

  test('is not offered when an env var, not the database, moved the value', () => {
    // The old gate was "value differs from the default", which offered Revert
    // for a field with nothing stored to revert — the DELETE was a no-op and
    // the value stayed exactly where it was.
    render(
      <ModuleForm
        module={moduleView([
          field({
            name: 'smtp_host',
            value: 'mail.example.com',
            default: 'localhost',
            env_set: true,
            env_readable: true,
          }),
        ])}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Revert' })).not.toBeInTheDocument();
  });

  test('is offered even when the stored override equals the default', () => {
    render(
      <ModuleForm
        module={moduleView([
          field({ name: 'smtp_host', value: 'localhost', default: 'localhost', db_override: true }),
        ])}
      />,
    );

    expect(screen.getByRole('button', { name: 'Revert' })).toBeVisible();
  });

  test('clears the override and reloads the props', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal('fetch', fetchMock);
    render(
      <ModuleForm
        module={moduleView([field({ name: 'smtp_host', value: 'mail.test', db_override: true })])}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Revert' }));

    await waitFor(() => expect(mocks.reload).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith('/api/settings/modules/users/smtp_host', {
      method: 'DELETE',
    });
  });
});

describe('Controls follow the declared field', () => {
  test('a boolean is a switch, not a checkbox', () => {
    render(
      <ModuleForm
        module={moduleView([field({ name: 'allow_signup', type: 'bool', value: true })])}
      />,
    );

    expect(screen.getByRole('switch')).toBeChecked();
  });

  test('a pattern-constrained string is a select over its choices', () => {
    render(
      <ModuleForm
        module={moduleView([
          field({
            name: 'mailer',
            value: 'smtp',
            default: 'console',
            choices: ['console', 'smtp'],
          }),
        ])}
      />,
    );

    expect(screen.getByRole('combobox')).toHaveTextContent('smtp');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  test('a secret is write-only, with a way to set a new one', () => {
    render(
      <ModuleForm
        module={moduleView([field({ name: 'smtp_password', value: '••••••••', is_secret: true })])}
      />,
    );

    expect(screen.getByText('write-only · never returned')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Set new value' })).toBeVisible();
  });
});

describe('Test connection', () => {
  test('names the single check it is about to run', () => {
    render(<ModuleForm module={moduleView([retentionDays])} checks={['users.mailer']} />);

    expect(screen.getByRole('button', { name: /Test mailer connection/ })).toBeVisible();
  });

  test('falls back to the generic label when a module registered several', () => {
    render(
      <ModuleForm
        module={moduleView([retentionDays])}
        checks={['users.mailer', 'users.storage']}
      />,
    );

    expect(screen.getByRole('button', { name: /Test connection/ })).toBeVisible();
  });

  test('is absent for a module with nothing to dial', () => {
    render(<ModuleForm module={moduleView([retentionDays])} />);

    expect(screen.queryByRole('button', { name: /Test/ })).not.toBeInTheDocument();
  });
});
