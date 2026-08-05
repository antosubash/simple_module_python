import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { Calendar } from './calendar';

// No page mounts Calendar today, so nothing else would catch a react-day-picker
// breaking change. v10 renamed the `table` class slot to `month_grid`; these
// tests pin the render contract so the next major upgrade fails loudly here.
describe('Calendar', () => {
  test('renders a month grid with day cells', () => {
    render(<Calendar month={new Date(2026, 0, 1)} />);
    // react-day-picker renders the grid as role=grid; day cells as gridcell.
    expect(screen.getByRole('grid')).toBeInTheDocument();
    expect(screen.getByText('January 2026')).toBeInTheDocument();
    expect(screen.getAllByRole('gridcell').length).toBeGreaterThan(27);
  });

  test('applies the month_grid class slot override', () => {
    const { container } = render(<Calendar month={new Date(2026, 0, 1)} />);
    const grid = container.querySelector('[role="grid"]');
    expect(grid?.className).toContain('border-collapse');
  });

  test('renders navigation chevrons', () => {
    render(<Calendar month={new Date(2026, 0, 1)} />);
    expect(screen.getByRole('button', { name: /previous/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument();
  });
});
