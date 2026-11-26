import { configureI18n } from '@simple-module-py/i18n';
import { ExtensionRegistry, ExtensionsProvider } from '@simple-module-py/ui/extensions';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import type { FieldMeta } from '../settings/ui/components/FieldInput';
import { ModuleFieldRow } from '../settings/ui/components/ModuleFieldRow';

configureI18n({ locale: 'en', messages: { 'settings.modules_form.invalid_json': 'Invalid JSON' } });
const field: FieldMeta = {
  name: 'setting',
  type: 'string',
  value: '',
  default: '',
  description: 'Help text.',
  is_secret: false,
  requires_restart: false,
  group: null,
  env_var: 'SM_TEST_SETTING',
};
function row(overrides: Partial<FieldMeta> = {}, error?: string) {
  const meta = { ...field, ...overrides };
  return (
    <ModuleFieldRow
      field={meta}
      package="test"
      value={meta.value}
      modified={false}
      error={error}
      onChange={() => {}}
      onReset={() => {}}
    />
  );
}

test.each<Partial<FieldMeta>>([
  {},
  { type: 'int', value: 1 },
  { type: 'bool', value: true },
  { type: 'bool', nullable: true },
  { choices: ['one'], value: 'one' },
  { type: 'json', value: {} },
  { is_secret: true },
  { control: 'custom' },
])('links and announces server errors for %j', (overrides) => {
  const registry = new ExtensionRegistry();
  registry.registerFieldRenderer('custom', ({ field, value, onChange, ...props }) => (
    <input
      {...props}
      value={String(value)}
      onChange={(event) => onChange(field.name, event.target.value)}
    />
  ));
  const { rerender } = render(
    <ExtensionsProvider registry={registry}>{row(overrides)}</ExtensionsProvider>,
  );
  rerender(
    <ExtensionsProvider registry={registry}>{row(overrides, 'Out of range')}</ExtensionsProvider>,
  );
  const control = screen.getByLabelText('setting');
  const description = screen.getByText('Help text.');
  const error = screen.getByRole('alert');
  expect(error).toHaveTextContent('Out of range');
  expect(error.id).not.toBe('');
  expect(control).toHaveAttribute('aria-describedby', `${description.id} ${error.id}`);
  expect(control).toHaveAttribute('aria-invalid', 'true');
  rerender(<ExtensionsProvider registry={registry}>{row(overrides)}</ExtensionsProvider>);
  expect(control).not.toHaveAttribute('aria-invalid', 'true');
  expect(control).toHaveAttribute('aria-describedby', description.id);
});

test('appends the JSON hint after description and server error, and removes it when valid', () => {
  render(row({ type: 'json', value: {} }, 'Rejected'));
  const control = screen.getByLabelText('setting');
  fireEvent.change(control, { target: { value: '{' } });
  const hint = screen.getByText('Invalid JSON');
  const description = screen.getByText('Help text.');
  const error = screen.getByText('Rejected');
  expect(hint.id).not.toBe('');
  expect(control).toHaveAttribute('aria-describedby', `${description.id} ${error.id} ${hint.id}`);
  expect(hint).toHaveAttribute('role', 'alert');
  fireEvent.change(control, { target: { value: '{}' } });
  expect(screen.queryByText('Invalid JSON')).not.toBeInTheDocument();
  expect(control).toHaveAttribute('aria-describedby', `${description.id} ${error.id}`);
  expect(control).toHaveAttribute('aria-invalid', 'true');
});
