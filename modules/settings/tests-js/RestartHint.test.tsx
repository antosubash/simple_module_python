import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'settings.modules_form.save': 'Save',
    'settings.modules_form.requires_restart': 'Requires restart',
    'settings.modules.heading_suffix': 'settings',
  },
});

vi.mock('@inertiajs/react', () => ({ router: { reload: vi.fn() } }));

import type { FieldMeta } from '../settings/pages/components/FieldInput';
import { ModuleForm } from '../settings/pages/components/ModuleForm';

// Build-time host settings (#499): an edit only applies after a restart, and
// the editor has to say so once the operator changes the value.
const tenantHeader: FieldMeta = {
  name: 'tenant_header',
  type: 'string',
  value: '',
  default: '',
  description: '',
  is_secret: false,
  requires_restart: true,
  group: 'Tenancy',
  env_var: 'SM_TENANT_HEADER',
  env_set: false,
  env_readable: false,
  db_override: false,
  choices: null,
};

describe('restart hint', () => {
  test('appears on a requires_restart field once it is edited', () => {
    render(
      <ModuleForm
        module={{
          module_name: 'Host',
          package: 'host',
          env_prefix: 'SM_',
          class_name: 'HostSettings',
          fields: [tenantHeader],
        }}
      />,
    );
    expect(screen.queryByText('Requires restart')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('tenant_header'), { target: { value: 'X-Tenant' } });

    expect(screen.getByText('Requires restart')).toBeVisible();
  });
});
