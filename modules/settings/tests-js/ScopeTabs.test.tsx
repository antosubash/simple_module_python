import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'settings.browse.scope_filter_label': 'Filter overrides by scope',
    'settings.browse.scope_all': 'All',
    'settings.scopes.system': 'system',
    'settings.scopes.tenant': 'tenant',
    'settings.scopes.user': 'user',
  },
});

import { type ScopeCounts, ScopeTabs } from '../settings/pages/components/ScopeTabs';

const counts: ScopeCounts = { all: 42, system: 28, tenant: 9, user: 5 };

function renderTabs(overrides: Partial<Parameters<typeof ScopeTabs>[0]> = {}) {
  const onChange = vi.fn();
  render(<ScopeTabs value="all" counts={counts} onChange={onChange} {...overrides} />);
  return onChange;
}

describe('ScopeTabs', () => {
  test('shows the server-side tally beside every scope', () => {
    renderTabs();

    expect(screen.getByRole('radio', { name: /^All\s*42$/ })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /^system\s*28$/ })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /^tenant\s*9$/ })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /^user\s*5$/ })).toBeInTheDocument();
  });

  test('marks only the selected scope as checked', () => {
    renderTabs({ value: 'tenant' });

    expect(screen.getByRole('radio', { name: /^tenant\s*9$/ })).toBeChecked();
    expect(screen.getByRole('radio', { name: /^All\s*42$/ })).not.toBeChecked();
  });

  test('reports the scope that was clicked', () => {
    const onChange = renderTabs();

    fireEvent.click(screen.getByRole('radio', { name: /^user\s*5$/ }));

    expect(onChange).toHaveBeenCalledWith('user');
  });

  test('a scope missing from the counts reads zero rather than blank', () => {
    // A tab that renders its count as nothing looks like a rendering bug; a
    // tab that disappears moves its neighbours under the cursor.
    render(
      <ScopeTabs value="all" counts={{ all: 1, system: 1 } as ScopeCounts} onChange={vi.fn()} />,
    );

    expect(screen.getByRole('radio', { name: /^user\s*0$/ })).toBeInTheDocument();
  });

  test('the group is labelled for screen readers', () => {
    renderTabs();

    expect(screen.getByRole('radiogroup', { name: 'Filter overrides by scope' })).toBeVisible();
  });
});
