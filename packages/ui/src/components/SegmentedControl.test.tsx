import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

import { SegmentedControl } from './SegmentedControl';

const OPTIONS = [
  { value: 'all', label: 'All', count: 12 },
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived', disabled: true },
];

describe('SegmentedControl', () => {
  test('renders one radio per option inside a labelled radiogroup', () => {
    render(
      <SegmentedControl
        value="all"
        onChange={() => {}}
        options={OPTIONS}
        aria-label="Filter by status"
      />,
    );
    expect(screen.getByRole('radiogroup', { name: 'Filter by status' })).toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(3);
  });

  test('marks only the selected option as checked', () => {
    render(
      <SegmentedControl
        value="active"
        onChange={() => {}}
        options={OPTIONS}
        aria-label="Filter by status"
      />,
    );
    expect(screen.getByRole('radio', { name: /Active/ })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: /All/ })).toHaveAttribute('aria-checked', 'false');
  });

  test('reports the picked value', () => {
    const onChange = vi.fn();
    render(
      <SegmentedControl
        value="all"
        onChange={onChange}
        options={OPTIONS}
        aria-label="Filter by status"
      />,
    );
    fireEvent.click(screen.getByRole('radio', { name: /Active/ }));
    expect(onChange).toHaveBeenCalledWith('active');
  });

  test('renders a count beside the option that carries one', () => {
    render(
      <SegmentedControl
        value="all"
        onChange={() => {}}
        options={OPTIONS}
        aria-label="Filter by status"
      />,
    );
    expect(screen.getByRole('radio', { name: /All/ })).toHaveTextContent('12');
  });

  test('the accessible name separates the label from the count', () => {
    // Without the separator the name read "All12" — one word, and unusable
    // as a target for anyone driving the page by voice.
    render(
      <SegmentedControl
        value="all"
        onChange={() => {}}
        options={OPTIONS}
        aria-label="Filter by status"
      />,
    );
    expect(screen.getByRole('radio', { name: 'All 12' })).toBeInTheDocument();
  });

  test('an option without a count keeps its label as its name', () => {
    render(
      <SegmentedControl
        value="all"
        onChange={() => {}}
        options={OPTIONS}
        aria-label="Filter by status"
      />,
    );
    expect(screen.getByRole('radio', { name: 'Active' })).toBeInTheDocument();
  });

  test('a disabled option cannot be picked', () => {
    const onChange = vi.fn();
    render(
      <SegmentedControl
        value="all"
        onChange={onChange}
        options={OPTIONS}
        aria-label="Filter by status"
      />,
    );
    const archived = screen.getByRole('radio', { name: /Archived/ });
    expect(archived).toBeDisabled();
    fireEvent.click(archived);
    expect(onChange).not.toHaveBeenCalled();
  });
});
