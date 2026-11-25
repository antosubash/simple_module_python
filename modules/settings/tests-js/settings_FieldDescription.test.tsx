import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import type { FieldMeta } from '../settings/ui/components/FieldInput';
import { ModuleFieldRow } from '../settings/ui/components/ModuleFieldRow';

configureI18n({ locale: 'en', messages: {} });

const field: FieldMeta = {
  name: 'setting',
  env_var: 'SM_EXAMPLE_SETTING',
  type: 'string',
  value: '',
  default: '',
  description: 'Help for this setting.',
  is_secret: false,
  requires_restart: false,
  group: null,
};

function row(meta: FieldMeta) {
  return (
    <ModuleFieldRow
      field={meta}
      package="example"
      value={meta.value}
      modified={false}
      onChange={() => {}}
      onReset={() => {}}
    />
  );
}

test.each([false, true])(
  'a boolean announces its description with db_override=%s',
  (db_override) => {
    render(row({ ...field, type: 'bool', value: false, db_override }));
    const control = screen.getByRole('switch', { name: 'setting' });
    const description = screen.getByText('Help for this setting.');
    expect(control).toHaveAccessibleDescription('Help for this setting.');
    expect(description.id).not.toBe('');
    expect(control).toHaveAttribute('aria-describedby', description.id);
    expect(screen.getByText('setting').parentElement?.contains(description)).toBe(db_override);
  },
);

test.each<[string, Partial<FieldMeta>, string]>([
  ['text', {}, 'textbox'],
  ['integer', { type: 'int', value: 1 }, 'spinbutton'],
  ['float', { type: 'float', value: 1.5 }, 'spinbutton'],
  ['JSON textarea', { type: 'json', value: {} }, 'textbox'],
  ['choices', { choices: ['one', 'two'], value: 'one' }, 'combobox'],
  ['nullable boolean', { type: 'bool', nullable: true, value: null }, 'combobox'],
])('a %s field announces its description', (_kind, overrides, role) => {
  render(row({ ...field, ...overrides }));
  const control = screen.getByRole(role, { name: 'setting' });
  const description = screen.getByText('Help for this setting.');
  expect(control).toHaveAccessibleDescription('Help for this setting.');
  expect(description.id).not.toBe('');
  expect(control).toHaveAttribute('aria-describedby', description.id);
});

test('a secret keeps its description when setting a new value', () => {
  render(row({ ...field, is_secret: true }));
  expect(screen.getByLabelText('setting')).toHaveAccessibleDescription('Help for this setting.');
  fireEvent.click(screen.getByRole('button'));
  expect(screen.getByRole('textbox', { name: 'setting' })).toHaveAccessibleDescription(
    'Help for this setting.',
  );
});

test('a field without a description has no aria-describedby', () => {
  render(row({ ...field, description: '' }));
  expect(screen.getByRole('textbox', { name: 'setting' })).not.toHaveAttribute('aria-describedby');
});

test('description IDs are unique per row and stable when the description moves columns', () => {
  const boolean = { ...field, type: 'bool' as const, value: false };
  const { rerender } = render(
    <>
      {row(boolean)}
      {row({ ...field, name: 'other' })}
    </>,
  );
  const control = screen.getByRole('switch', { name: 'setting' });
  const descriptionId = control.getAttribute('aria-describedby');
  expect(descriptionId).toBeTruthy();
  expect(screen.getByRole('textbox', { name: 'other' }).getAttribute('aria-describedby')).not.toBe(
    descriptionId,
  );
  rerender(
    <>
      {row({ ...boolean, db_override: true })}
      {row({ ...field, name: 'other' })}
    </>,
  );
  expect(control).toHaveAttribute('aria-describedby', descriptionId);
  expect(control).toHaveAccessibleDescription('Help for this setting.');
});
