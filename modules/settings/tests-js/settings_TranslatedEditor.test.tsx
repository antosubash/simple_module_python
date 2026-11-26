import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'settings.modules_form.save': 'Save',
    'settings.modules_form.discard': 'Discard',
    'settings.modules_form.reset_to_default': 'Reset to default',
    'settings.modules_form.revert_field': 'Reset {field} to default',
    'settings.modules.source_default': 'Default',
    'settings.modules.source_unsaved': 'Unsaved',
    'settings.modules.source_env': 'Set by environment',
    'settings.modules.source_db': 'Overridden',
    'settings.modules.source_db_ignored_for_env': 'Stored · environment wins',
    'settings.modules.secret_write_only': 'Write-only',
    'settings.modules.default_value': 'Default: {value}',
    'settings.modules.unsaved_count_one': '{count} unsaved change',
    'settings.modules.unsaved_count_other': '{count} unsaved changes',
    'mail.settings_form.title': 'Mail',
    'mail.settings_form.description': 'How the app sends email.',
    'mail.settings_form.groups.smtp_account': 'SMTP account',
    'mail.settings_form.fields.smtp_host.label': 'SMTP server',
    'mail.settings_form.fields.smtp_host.help': 'Host name of your mail server.',
    'mail.settings_form.fields.smtp_port.label': 'Port',
    'mail.settings_form.fields.backend.choices.console': 'Console (log only)',
    'settings.modules_form.option_on': 'On',
    'settings.modules_form.option_off': 'Off',
    'settings.modules.test_connection': 'Test {name} connection',
  },
});

vi.mock('@inertiajs/react', () => ({ router: { reload: vi.fn() } }));

import type { FieldMeta } from '../settings/ui/components/FieldInput';
import { FieldSource } from '../settings/ui/components/FieldSource';
import { ModuleForm } from '../settings/ui/components/ModuleForm';
import { TestConnectionButton } from '../settings/ui/components/TestConnectionButton';

function field(overrides: Partial<FieldMeta> & { name: string }): FieldMeta {
  return {
    type: 'string',
    value: '',
    default: '',
    description: '',
    is_secret: false,
    requires_restart: false,
    group: null,
    env_var: `SM_MAIL_${overrides.name.toUpperCase()}`,
    ...overrides,
  };
}

function renderMail(fields: FieldMeta[]) {
  return render(
    <ModuleForm
      module={{
        module_name: 'Mail',
        package: 'mail',
        env_prefix: 'SM_MAIL_',
        class_name: 'MailSettings',
        fields,
      }}
    />,
  );
}

describe('translated editor', () => {
  test('labels, help, group headings and the module title come from settings_form keys', () => {
    renderMail([
      field({ name: 'backend', value: 'console' }),
      field({ name: 'smtp_host', group: 'SMTP account', description: 'Python text' }),
      field({ name: 'smtp_port', type: 'int', value: 587, default: 587, group: 'SMTP account' }),
    ]);
    expect(screen.getByRole('heading', { level: 2, name: 'Mail' })).toBeVisible();
    expect(screen.getByText('How the app sends email.')).toBeVisible();
    expect(screen.getByRole('heading', { level: 3, name: 'SMTP account' })).toBeVisible();
    expect(screen.getByLabelText('SMTP server')).toHaveAccessibleDescription(
      'Host name of your mail server.',
    );
    expect(screen.queryByText('Python text')).not.toBeInTheDocument();
    // No key: humanised, never the raw identifier.
    expect(screen.getByLabelText('Backend')).toBeInTheDocument();
    expect(screen.queryByText('smtp_host')).not.toBeInTheDocument();
  });

  test('ungrouped fields come first', () => {
    renderMail([field({ name: 'smtp_host', group: 'SMTP account' }), field({ name: 'backend' })]);
    const labels = screen.getAllByText(/Backend|SMTP server/).map((el) => el.textContent);
    expect(labels).toEqual(['Backend', 'SMTP server']);
  });

  test('an edit marks the row unsaved and Discard restores the saved value', () => {
    renderMail([field({ name: 'smtp_host', value: 'saved.example', default: 'saved.example' })]);
    const input = screen.getByLabelText('SMTP server');
    fireEvent.change(input, { target: { value: 'draft.example' } });
    expect(screen.getByText('Unsaved')).toBeVisible();
    expect(screen.getByText('Default: saved.example')).toBeVisible();
    expect(screen.getByText('1 unsaved change')).toBeVisible();

    const discard = screen.getByRole('button', { name: 'Discard' });
    discard.focus();
    fireEvent.click(discard);
    expect(input).toHaveValue('saved.example');
    expect(screen.queryByText('Unsaved')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Discard' })).not.toBeInTheDocument();
    // The focused Discard button unmounted; focus lands on the module heading.
    expect(screen.getByRole('heading', { level: 2, name: 'Mail' })).toHaveFocus();
  });
});

describe('source badge', () => {
  function source(overrides: Partial<FieldMeta>, value: unknown = '') {
    const meta = field({ name: 'smtp_host', ...overrides });
    render(
      <FieldSource
        field={meta}
        label="SMTP server"
        value={value}
        modified={false}
        onReset={() => {}}
      />,
    );
  }

  test.each<[string, Partial<FieldMeta>, string]>([
    ['default', {}, 'Default'],
    ['stored override', { db_override: true }, 'Overridden'],
    ['env value', { env_set: true }, 'Set by environment'],
    ['stored but env wins', { env_set: true, db_override: true }, 'Stored · environment wins'],
    ['secret', { is_secret: true }, 'Write-only'],
  ])('%s', (_name, overrides, badge) => {
    source(overrides);
    expect(screen.getByText(badge)).toBeVisible();
  });

  test('names the env var only when that exact variable supplies the value', () => {
    source({ env_set: true, env_source_var: 'SM_MAIL_SMTP_HOST' });
    expect(screen.getByText('SM_MAIL_SMTP_HOST')).toBeVisible();
  });

  test('an env value from another variable gets the badge but no name', () => {
    source({ env_set: true });
    expect(screen.getByText('Set by environment')).toBeVisible();
    expect(screen.queryByText('SM_MAIL_SMTP_HOST')).not.toBeInTheDocument();
  });

  test('a DB-only field never shows its env var label', () => {
    source({});
    expect(screen.queryByText('SM_MAIL_SMTP_HOST')).not.toBeInTheDocument();
  });

  test('a stored override offers Reset named after the label, and shows the default', () => {
    source({ db_override: true, default: 'localhost' }, 'mail.example');
    const line = screen.getByText('Overridden').parentElement as HTMLElement;
    expect(
      within(line).getByRole('button', { name: 'Reset SMTP server to default' }),
    ).toBeVisible();
    expect(within(line).getByText('Default: localhost')).toBeVisible();
  });

  test('env pinning a stored field offers no Reset the server would refuse', () => {
    source({ env_set: true, db_override: true });
    expect(screen.getByText('Stored · environment wins')).toBeVisible();
    expect(screen.queryByRole('button', { name: /Reset/ })).not.toBeInTheDocument();
  });
});

test('a moved value shows its default the way the control labels it', () => {
  renderMail([
    field({ name: 'backend', value: 'smtp', default: 'console', choices: ['console', 'smtp'] }),
    field({ name: 'smtp_tls', type: 'bool', value: false, default: true, db_override: true }),
  ]);
  expect(screen.getByText('Default: Console (log only)')).toBeVisible();
  expect(screen.getByText('Default: On')).toBeVisible();
});

test('a single connection check is named after the translated module, not its check id', () => {
  render(<TestConnectionButton pkg="mail" checks={['mail.mailer']} title="E-Mail" />);
  expect(screen.getByRole('button', { name: 'Test E-Mail connection' })).toBeVisible();
});
