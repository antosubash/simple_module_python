import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'audit_log.browse.no_match_title': 'No entries match these filters',
    'audit_log.browse.clear_filters': 'Clear filters',
    'audit_log.filters.tenant_label': 'Tenant',
    'audit_log.filters.tenant_platform': 'Platform',
  },
});

import { BrowseEmpty } from '../audit_log/pages/components/BrowseEmpty';

const NONE = {
  entity_type: null,
  action: null,
  tenant_id: null,
  user_id: null,
  correlation_id: null,
  from_date: null,
  to_date: null,
};

function renderWith(tenantId: string) {
  render(
    <BrowseEmpty
      applied={{ ...NONE, tenant_id: tenantId }}
      entityTypes={[]}
      platformTenantValue="__platform__"
      onClear={() => {}}
    />,
  );
}

describe('BrowseEmpty tenant summary', () => {
  test('the platform filter is named, never shown as its sentinel', () => {
    renderWith('__platform__');

    expect(screen.getByText('Tenant: Platform')).toBeInTheDocument();
    expect(screen.queryByText(/__platform__/)).not.toBeInTheDocument();
  });

  test('a real tenant id is shown as is', () => {
    renderWith('acme');

    expect(screen.getByText('Tenant: acme')).toBeInTheDocument();
  });
});
