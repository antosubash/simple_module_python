import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'settings.modules.title': 'Module Settings',
    'settings.modules.head_title': 'Module settings',
    'settings.modules.search_placeholder': 'Search modules…',
    'settings.modules.empty_title': 'No modules with settings',
    'settings.modules.managed_title': 'Managed on its own page',
  },
});

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children, ...rest }: { children?: unknown }) => <a {...rest}>{children as never}</a>,
  router: { reload: vi.fn() },
}));

vi.mock('@simple-module-py/ui/layouts/AdminLayout', () => ({ AdminLayout: () => null }));

import ModulesEdit from '../settings/pages/ModulesEdit';

describe('ModulesEdit', () => {
  test('has one level-1 heading naming the screen, even with no modules', () => {
    render(<ModulesEdit modules={[]} />);

    const h1 = screen.getAllByRole('heading', { level: 1 });
    expect(h1).toHaveLength(1);
    expect(h1[0]).toHaveTextContent('Module Settings');
    // Visible, like the other admin pages' headings (#422), not screen-reader-only.
    expect(h1[0]).not.toHaveClass('sr-only');
  });

  test('keeps the single h1 when a module is managed elsewhere', () => {
    render(
      <ModulesEdit
        modules={[
          {
            package: 'branding',
            module_name: 'Branding',
            manage_url: '/admin/branding/',
            fields: [],
          } as never,
        ]}
      />,
    );

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });
  test('does not list a module with no fields and no manage_url, and skips it initially', () => {
    render(
      <ModulesEdit
        modules={[
          { package: 'alpha', module_name: 'Alpha', manage_url: null, fields: [] } as never,
          {
            package: 'beta',
            module_name: 'Beta',
            manage_url: null,
            fields: [{ name: 'x', db_override: false }],
          } as never,
        ]}
      />,
    );

    expect(screen.queryByText('alpha')).not.toBeInTheDocument();
    expect(screen.getAllByText('beta').length).toBeGreaterThan(1); // list + selected form
    // Initial selection is the first *visible* module, not the hidden one.
    expect(screen.queryByText('No modules with settings')).not.toBeInTheDocument();
  });

  test('still lists a zero-field module that has a manage_url', () => {
    render(
      <ModulesEdit
        modules={[
          { package: 'branding', module_name: 'Branding', manage_url: '/x/', fields: [] } as never,
        ]}
      />,
    );

    expect(screen.getByText('branding')).toBeInTheDocument();
  });
});
