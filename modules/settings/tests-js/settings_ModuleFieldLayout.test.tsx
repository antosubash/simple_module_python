import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import type { FieldMeta } from '../settings/ui/components/FieldInput';
import { ModuleFieldRow } from '../settings/ui/components/ModuleFieldRow';
import { ModuleForm } from '../settings/ui/components/ModuleForm';

configureI18n({ locale: 'en', messages: {} });

const field: FieldMeta = {
  name: 'very_long_underscore_separated_setting_name',
  env_var: 'SM_FILE_STORAGE_VERY_LONG_UNDERSCORE_SEPARATED_SETTING_NAME',
  type: 'string',
  value: '',
  default: '',
  description: '',
  is_secret: false,
  requires_restart: false,
  group: null,
};

// jsdom has no layout engine: these guard the responsive CSS contract.
test('the editor card supplies the field rows container width', () => {
  const { container } = render(
    <ModuleForm
      module={{
        module_name: 'FileStorage',
        package: 'file_storage',
        env_prefix: 'SM_FILE_STORAGE_',
        class_name: 'FileStorageSettings',
        fields: [field],
      }}
    />,
  );
  expect(container.querySelector('[data-slot="card"]')).toHaveClass('@container');
});

test('rows bound their tracks and wrap identifiers without viewport breakpoints', () => {
  const { container } = render(
    <ModuleFieldRow
      field={field}
      package="file_storage"
      value=""
      modified={false}
      error="Invalid setting"
      onChange={() => {}}
      onReset={() => {}}
    />,
  );
  const row = container.firstElementChild;
  expect(row).toHaveClass('grid-cols-1', '@2xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]');
  expect(row?.className).not.toMatch(/(?:^|\s)(?:sm|md|lg|xl):/);
  // The label is humanised, never the raw identifier, and still wraps.
  const label = screen.getByText('Very long underscore separated setting name');
  expect(label).toHaveClass('[overflow-wrap:anywhere]');
  expect(label).toHaveAttribute('title', field.name);
  expect(screen.queryByText(field.env_var)).not.toBeInTheDocument();
  expect(screen.getByText('Invalid setting')).toHaveClass('@2xl:col-start-2');
});

test('an env-supplied field names its env var and lets it wrap', () => {
  render(
    <ModuleFieldRow
      field={{ ...field, env_set: true }}
      package="file_storage"
      value=""
      modified={false}
      onChange={() => {}}
      onReset={() => {}}
    />,
  );
  expect(screen.getByText(field.env_var)).toHaveClass('[overflow-wrap:anywhere]');
});
