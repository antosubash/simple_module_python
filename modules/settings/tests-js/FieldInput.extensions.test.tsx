import { configureI18n } from '@simple-module-py/i18n';
import { ExtensionRegistry, ExtensionsProvider } from '@simple-module-py/ui/extensions';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FieldInput, type FieldMeta } from '../settings/ui/components/FieldInput';

configureI18n({ locale: 'en', messages: {} });

afterEach(cleanup);
const field: FieldMeta = {
  name: 'date',
  type: 'string',
  value: '',
  default: '',
  description: '',
  is_secret: false,
  requires_restart: false,
  group: null,
  env_var: '',
  control: 'date',
};

it('uses a registered control with the field metadata and change callback', () => {
  const registry = new ExtensionRegistry();
  registry.registerFieldRenderer('date', ({ field, value, onChange, id, ...props }) => (
    <input
      {...props}
      id={id}
      type="date"
      value={String(value)}
      onChange={(event) => onChange(field.name, event.target.value)}
    />
  ));
  const onChange = vi.fn();
  const view = render(
    <ExtensionsProvider registry={registry}>
      <p id="date-help">Choose a date.</p>
      <FieldInput
        field={field}
        value="2026-11-18"
        id="date-field"
        aria-describedby="date-help"
        onChange={onChange}
      />
    </ExtensionsProvider>,
  );
  const input = view.container.querySelector('input');
  expect(input).toHaveAttribute('type', 'date');
  expect(input).toHaveAttribute('id', 'date-field');
  expect(input).toHaveAccessibleDescription('Choose a date.');
  fireEvent.change(input as HTMLInputElement, { target: { value: '2026-12-01' } });
  expect(onChange).toHaveBeenCalledWith('date', '2026-12-01');
});

it.each([undefined, 'unknown'])('falls back to built-in controls for %s', (control) => {
  render(
    <ExtensionsProvider registry={new ExtensionRegistry()}>
      <FieldInput field={{ ...field, control }} value="original" onChange={() => {}} />
    </ExtensionsProvider>,
  );
  expect(screen.getByRole('textbox')).toHaveValue('original');
});

it('keeps secret fields masked before invoking a custom renderer', () => {
  const registry = new ExtensionRegistry();
  registry.registerFieldRenderer('date', () => <p>custom renderer</p>);
  const view = render(
    <ExtensionsProvider registry={registry}>
      <FieldInput field={{ ...field, is_secret: true }} value="masked" onChange={() => {}} />
    </ExtensionsProvider>,
  );
  expect(view.container.querySelector('input')).toHaveAttribute('type', 'password');
  expect(screen.queryByText('custom renderer')).not.toBeInTheDocument();
});
