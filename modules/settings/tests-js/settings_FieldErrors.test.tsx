import { configureI18n } from '@simple-module-py/i18n';
import { ExtensionRegistry, ExtensionsProvider } from '@simple-module-py/ui/extensions';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import type { FieldMeta } from '../settings/ui/components/FieldInput';
import { ModuleFieldRow } from '../settings/ui/components/ModuleFieldRow';
import { ModuleForm } from '../settings/ui/components/ModuleForm';

vi.mock('@inertiajs/react', () => ({ router: { reload: vi.fn() } }));
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
  rerender(
    <ExtensionsProvider registry={registry}>{row(overrides, 'Out of range')}</ExtensionsProvider>,
  );
  expect(screen.getByRole('alert')).toBe(error);
  rerender(<ExtensionsProvider registry={registry}>{row(overrides)}</ExtensionsProvider>);
  expect(control).not.toHaveAttribute('aria-invalid', 'true');
  expect(control).toHaveAttribute('aria-describedby', description.id);
});

test.each([false, true])(
  'only describes mounted feedback without a description (error=%s)',
  (hasError) => {
    render(row({ description: '' }, hasError ? 'Rejected' : undefined));
    const control = screen.getByLabelText('setting');
    const ids = control.getAttribute('aria-describedby')?.split(' ') ?? [];
    expect(ids).toHaveLength(hasError ? 1 : 0);
    for (const id of ids) expect(document.getElementById(id)).toHaveTextContent('Rejected');
  },
);

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

test('a rejected save focuses the first invalid field and editing clears its error', async () => {
  const detail = [{ loc: ['setting'], msg: 'Out of range' }];
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 422 })),
  );
  const fields = [{ ...field, name: 'first' }, field];
  render(
    <ModuleForm
      module={{
        package: 'test',
        module_name: 'Test',
        env_prefix: 'SM_TEST_',
        class_name: 'TestSettings',
        fields,
      }}
    />,
  );
  const control = screen.getByLabelText('setting');
  fireEvent.change(control, { target: { value: 'bad' } });
  fireEvent.click(screen.getByRole('button', { name: /save/i }));
  await waitFor(() => expect(control).toHaveAttribute('aria-invalid', 'true'));
  // Focus moves in a passive effect after the error render commits, so wait
  // for it rather than asserting in the same tick (#1183).
  await waitFor(() => expect(control).toHaveFocus());
  fireEvent.change(control, { target: { value: 'better' } });
  expect(control).not.toHaveAttribute('aria-invalid', 'true');
  expect(screen.queryByText('Out of range')).not.toBeInTheDocument();
  vi.unstubAllGlobals();
});
