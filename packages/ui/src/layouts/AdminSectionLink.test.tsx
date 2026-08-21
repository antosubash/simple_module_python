import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import type { MenuItem } from '../types';

// Mock @simple-module-py/i18n so useT resolves the nav.admin key without a
// real i18next instance — same pattern LocaleSwitcher.test.tsx uses.
vi.mock('@simple-module-py/i18n', () => ({
  useT: () => ({
    t: (key: string) => (key === 'ui.nav.admin' ? 'Administration' : key),
  }),
  keys: {
    ui: {
      nav: {
        admin: 'ui.nav.admin',
      },
    },
  },
}));

import { AdminSectionLink } from './AdminSectionLink';

const adminItem: MenuItem = { label: 'Users', url: '/admin/users/', icon: 'users' };

describe('AdminSectionLink', () => {
  test('renders a link to /admin when the viewer has admin entries', () => {
    render(<AdminSectionLink adminItems={[adminItem]} className="" onNavigate={() => {}} />);
    const link = screen.getByRole('link', { name: 'Administration' });
    expect(link).toHaveAttribute('href', '/admin');
  });

  test('renders nothing when the viewer has no admin entries', () => {
    const { container } = render(
      <AdminSectionLink adminItems={[]} className="" onNavigate={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
