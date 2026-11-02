import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import type { FieldMeta } from '../settings/pages/components/FieldInput';
import { ModuleFieldRow } from '../settings/pages/components/ModuleFieldRow';
import { ModuleForm } from '../settings/pages/components/ModuleForm';

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
  expect(container.querySelector('[data-slot="card"]')).toHaveClass('@container', 'min-w-0');
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
  expect(row).toHaveClass(
    'grid-cols-1',
    '@md:grid-cols-[minmax(0,140px)_minmax(180px,1fr)]',
    '@xl:grid-cols-[minmax(0,140px)_minmax(180px,1fr)_minmax(0,160px)]',
  );
  expect(row?.className).not.toMatch(/(?:^|\s)(?:sm|lg):/);
  expect(screen.getByText(field.name)).toHaveClass('[overflow-wrap:anywhere]');
  const source = screen.getByText(field.env_var);
  expect(source).toHaveClass('[overflow-wrap:anywhere]');
  expect(source.parentElement).toHaveClass('min-w-0', '@md:col-span-2', '@xl:col-span-1');
  expect(screen.getByText('Invalid setting')).toHaveClass('@md:col-start-2', '@xl:col-span-2');
});
