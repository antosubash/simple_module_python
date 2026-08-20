import { render, screen } from '@testing-library/react';
import { Inbox } from 'lucide-react';
import { describe, expect, test } from 'vitest';

import { EmptyState } from './EmptyState';

describe('EmptyState', () => {
  test('renders the title', () => {
    render(<EmptyState icon={Inbox} title="No task has run yet" />);
    expect(screen.getByText('No task has run yet')).toBeInTheDocument();
  });

  test('shows the optional description', () => {
    render(
      <EmptyState
        icon={Inbox}
        title="No task has run yet"
        description="Registered tasks appear here the first time they execute."
      />,
    );
    expect(screen.getByText(/first time they execute/i)).toBeInTheDocument();
  });

  test('omits the description when not given', () => {
    const { container } = render(<EmptyState icon={Inbox} title="Nothing here" />);
    expect(container.querySelector('[data-slot="empty-description"]')).toBeNull();
  });

  test('places the call to action', () => {
    render(
      <EmptyState
        icon={Inbox}
        title="No entries match these filters"
        action={<button type="button">Clear filters</button>}
      />,
    );
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  });

  test('omits the action slot when there is nothing to do', () => {
    const { container } = render(<EmptyState icon={Inbox} title="Nothing here" />);
    expect(container.querySelector('[data-slot="empty-content"]')).toBeNull();
  });

  test('hides the decorative icon from assistive tech', () => {
    const { container } = render(<EmptyState icon={Inbox} title="Nothing here" />);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
});
