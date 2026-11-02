import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
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

/** Controlled wrapper, so a keyboard move is reflected the way a page would. */
function Harness({ initial = 'all' }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return (
    <SegmentedControl
      value={value}
      onChange={setValue}
      options={OPTIONS}
      aria-label="Filter by status"
    />
  );
}

describe('SegmentedControl keyboard', () => {
  test('the whole group is one tab stop, parked on the checked option', async () => {
    const user = userEvent.setup();
    render(
      <>
        <Harness initial="active" />
        <button type="button">after</button>
      </>,
    );

    await user.tab();
    expect(screen.getByRole('radio', { name: 'Active' })).toHaveFocus();

    // One more Tab leaves the group entirely rather than stepping to the next
    // chip: that is the difference the roving tabIndex buys.
    await user.tab();
    expect(screen.getByRole('button', { name: 'after' })).toHaveFocus();
  });

  test('arrow keys move focus and selection together', async () => {
    const user = userEvent.setup();
    render(<Harness initial="all" />);

    await user.tab();
    await user.keyboard('{ArrowRight}');

    const active = screen.getByRole('radio', { name: 'Active' });
    expect(active).toHaveFocus();
    expect(active).toHaveAttribute('aria-checked', 'true');
  });

  test('arrow keys skip disabled options and wrap round the ends', async () => {
    const user = userEvent.setup();
    render(<Harness initial="active" />);

    // Right from "Active" would land on the disabled "Archived", so it wraps
    // past it to "All".
    await user.tab();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: 'All 12' })).toHaveFocus();

    // And left from "All" wraps backwards, skipping "Archived" again.
    await user.keyboard('{ArrowLeft}');
    expect(screen.getByRole('radio', { name: 'Active' })).toHaveFocus();
  });

  test('Home and End jump to the first and last enabled options', async () => {
    const user = userEvent.setup();
    render(<Harness initial="active" />);

    await user.tab();
    await user.keyboard('{Home}');
    expect(screen.getByRole('radio', { name: 'All 12' })).toHaveFocus();

    // "Archived" is disabled, so the last *reachable* option is "Active".
    await user.keyboard('{End}');
    expect(screen.getByRole('radio', { name: 'Active' })).toHaveFocus();
  });

  test('a group whose value matches nothing is still reachable by Tab', async () => {
    const user = userEvent.setup();
    render(
      <SegmentedControl
        value="gone"
        onChange={() => {}}
        options={OPTIONS}
        aria-label="Filter by status"
      />,
    );

    await user.tab();
    expect(screen.getByRole('radio', { name: 'All 12' })).toHaveFocus();
  });
});
