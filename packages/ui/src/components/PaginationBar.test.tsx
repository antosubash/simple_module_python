import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

vi.mock('@simple-module-py/i18n', () => ({
  useT: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      key === 'ui.pagination.showing'
        ? `Showing ${vars?.from}–${vars?.to} of ${vars?.total}`
        : ({ 'ui.pagination.previous': 'Previous', 'ui.pagination.next': 'Next' }[key] ?? key),
  }),
  keys: {
    ui: {
      pagination: {
        showing: 'ui.pagination.showing',
        previous: 'ui.pagination.previous',
        next: 'ui.pagination.next',
      },
    },
  },
}));

import { PaginationBar } from './PaginationBar';

describe('PaginationBar', () => {
  test('shows the slice and pages forward and back', () => {
    const onPageChange = vi.fn();
    render(<PaginationBar page={2} perPage={10} total={25} onPageChange={onPageChange} />);
    expect(screen.getByText('Showing 11–20 of 25')).toBeTruthy();
    fireEvent.click(screen.getByText('Next'));
    fireEvent.click(screen.getByText('Previous'));
    expect(onPageChange).toHaveBeenNthCalledWith(1, 3);
    expect(onPageChange).toHaveBeenNthCalledWith(2, 1);
  });

  test('disables Previous on the first page and Next on the last', () => {
    const { rerender } = render(
      <PaginationBar page={1} perPage={10} total={25} onPageChange={() => {}} />,
    );
    expect((screen.getByText('Previous') as HTMLButtonElement).disabled).toBe(true);
    rerender(<PaginationBar page={3} perPage={10} total={25} onPageChange={() => {}} />);
    expect((screen.getByText('Next') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('Showing 21–25 of 25')).toBeTruthy();
  });

  test('an empty list reads 0–0 and Next is disabled', () => {
    render(<PaginationBar page={1} perPage={10} total={0} onPageChange={() => {}} />);
    expect(screen.getByText('Showing 0–0 of 0')).toBeTruthy();
    expect((screen.getByText('Next') as HTMLButtonElement).disabled).toBe(true);
  });

  test('hideWhenSinglePage renders nothing for one page', () => {
    const { container } = render(
      <PaginationBar page={1} perPage={10} total={5} hideWhenSinglePage onPageChange={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
