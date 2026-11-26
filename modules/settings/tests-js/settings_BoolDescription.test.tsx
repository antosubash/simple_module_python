import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import type { FieldMeta } from '../settings/ui/components/FieldInput';
import { ModuleFieldRow } from '../settings/ui/components/ModuleFieldRow';

configureI18n({ locale: 'en', messages: {} });

const WARNING = 'Turning this on lets managers reach internal addresses.';

const boolField: FieldMeta = {
  name: 'allow_internal',
  env_var: 'SM_EVENTS_ALLOW_INTERNAL',
  type: 'bool',
  value: false,
  default: false,
  description: WARNING,
  is_secret: false,
  requires_restart: false,
  group: null,
};

function renderRow(field: FieldMeta) {
  render(
    <ModuleFieldRow
      field={field}
      package="events"
      value={field.value}
      modified={false}
      onChange={() => {}}
      onReset={() => {}}
    />,
  );
}

test('a bool description shows once, under its label, without a stored value', () => {
  renderRow(boolField);
  expect(screen.getAllByText(WARNING)).toHaveLength(1);
  expect(screen.getByText('Allow internal').parentElement).toContainElement(
    screen.getByText(WARNING),
  );
});

// #1062: the stored-value text takes the trailing column over; the warning must stay on the row.
test('a bool description stays on the row while a stored value overrides it', () => {
  renderRow({ ...boolField, value: true, db_override: true });
  expect(screen.getAllByText(WARNING)).toHaveLength(1);
  expect(screen.getByText('Allow internal').parentElement).toContainElement(
    screen.getByText(WARNING),
  );
});

test('a bool input_type field keeps its description when overridden', () => {
  renderRow({ ...boolField, type: 'string', input_type: 'bool', db_override: true });
  expect(screen.getAllByText(WARNING)).toHaveLength(1);
});
