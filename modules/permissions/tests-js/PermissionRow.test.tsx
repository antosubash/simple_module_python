import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import { PermissionRow } from '../permissions/pages/components/PermissionRow';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub);

configureI18n({
  locale: 'en',
  messages: {
    'permissions.user_edit.direct_toggle_label': 'Grant {key} directly to this user',
    'permissions.user_edit.direct_badge': 'direct',
  },
});

describe('PermissionRow', () => {
  test('shows the key beside a source label and names the switch after the key', () => {
    render(
      <PermissionRow
        permissionKey="records.admin.delete"
        label="Harmless read access"
        direct={false}
        viaRoles={[]}
        onToggle={() => {}}
      />,
    );

    expect(screen.getByText('Harmless read access')).toBeVisible();
    expect(screen.getByText('records.admin.delete', { selector: 'code' })).toBeVisible();
    expect(
      screen.getByRole('switch', { name: 'Grant records.admin.delete directly to this user' }),
    ).toBeVisible();
  });

  test('ignores a blank label and shows only the key', () => {
    render(
      <PermissionRow
        permissionKey="records.faq.edit"
        label="   "
        direct={false}
        viaRoles={[]}
        onToggle={() => {}}
      />,
    );

    const code = screen.getByText('records.faq.edit', { selector: 'code' });
    expect(code).toBeVisible();
    expect(code.parentElement?.children).toHaveLength(1);
  });
});
