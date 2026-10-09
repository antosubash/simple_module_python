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
});
