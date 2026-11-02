import { configureI18n, keys } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });
vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { visit: vi.fn() },
  usePage: () => ({ props: {} }),
}));

import Browse from '../audit_log/pages/Browse';

const props: ComponentProps<typeof Browse> = {
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
  entity_types: [],
  tenant_ids: [],
  platform_tenant_value: '__platform__',
  export_url: '/api/audit_log/export',
  filters: {
    entity_type: null,
    action: null,
    tenant_id: null,
    user_id: null,
    correlation_id: null,
    from_date: null,
    to_date: null,
  },
};

describe('audit_log Browse', () => {
  it('mounts the filter form, empty state, and export link', () => {
    render(<Browse {...props} />);
    expect(screen.getByRole('heading', { name: keys.audit_log.browse.title })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: keys.audit_log.filters.apply })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: keys.audit_log.browse.export_csv })).toHaveAttribute(
      'download',
    );
    expect(screen.getByRole('button', { name: keys.ui.pagination.next })).toBeDisabled();
  });

  it('mounts a populated entry with its resolved actor and resource', () => {
    render(
      <Browse
        {...props}
        total={1}
        items={[
          {
            id: 'audit-1',
            entity_type: 'Note',
            entity_id: 'note-1',
            action: 'created',
            changes: [],
            user_id: 'user-1',
            actor: 'Alice',
            actor_url: null,
            entity: {
              display: 'Meeting notes',
              url: null,
              label: 'Note',
              table_name: 'notes_note',
            },
            correlation_id: null,
            tenant_id: 'acme',
            created_at: '2026-10-01T12:00:00Z',
          },
        ]}
      />,
    );
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Meeting notes')).toBeInTheDocument();
    expect(screen.getByRole('table')).toBeInTheDocument();
  });
});
