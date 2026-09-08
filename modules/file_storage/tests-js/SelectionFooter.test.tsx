/**
 * `modules/file_storage` shipped with no `.test.tsx` at all.
 *
 * `SelectionFooter` is the piece worth pinning first: it is always rendered —
 * even for a single page, because the range is the answer to "did my filter
 * match anything?" — and it computes four numbers off two, which is where an
 * off-by-one lives.
 */
import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';
import { SelectionFooter } from '../file_storage/pages/components/SelectionFooter';

configureI18n({
  locale: 'en',
  messages: {
    'file_storage.browse.showing': 'Showing {from}–{to} of {total}',
    'file_storage.browse.selected_showing': '{count} selected · showing {from}–{to} of {total}',
    'file_storage.browse.previous': 'Previous',
    'file_storage.browse.next': 'Next',
  },
});

function renderFooter(
  pagination: { page: number; perPage: number; total: number },
  selectedCount = 0,
) {
  const onGo = vi.fn();
  render(<SelectionFooter pagination={pagination} selectedCount={selectedCount} onGo={onGo} />);
  return { onGo };
}

describe('the range it reports', () => {
  test('the first of several pages', () => {
    renderFooter({ page: 1, perPage: 20, total: 45 });

    expect(screen.getByText('Showing 1–20 of 45')).toBeInTheDocument();
  });

  test('a last page that is not full stops at the total', () => {
    renderFooter({ page: 3, perPage: 20, total: 45 });

    expect(screen.getByText('Showing 41–45 of 45')).toBeInTheDocument();
  });

  test('an empty result reads 0–0, not 1–0', () => {
    renderFooter({ page: 1, perPage: 20, total: 0 });

    expect(screen.getByText('Showing 0–0 of 0')).toBeInTheDocument();
  });

  test('a selection is named alongside the range, not instead of it', () => {
    renderFooter({ page: 1, perPage: 20, total: 45 }, 3);

    expect(screen.getByText('3 selected · showing 1–20 of 45')).toBeInTheDocument();
  });
});

describe('the pager', () => {
  test('it is rendered even when everything fits on one page', () => {
    // Deliberate: a pager that only appears past twenty rows makes people
    // wonder whether it exists at all.
    renderFooter({ page: 1, perPage: 20, total: 3 });

    expect(screen.getByRole('button', { name: 'Previous' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument();
  });

  test('both ends are disabled when there is a single page', () => {
    renderFooter({ page: 1, perPage: 20, total: 3 });

    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  test('the middle of a run can go both ways', async () => {
    const user = userEvent.setup();
    const { onGo } = renderFooter({ page: 2, perPage: 20, total: 45 });

    await user.click(screen.getByRole('button', { name: 'Previous' }));
    expect(onGo).toHaveBeenCalledWith(1);

    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(onGo).toHaveBeenCalledWith(3);
  });

  test('an exact multiple does not offer an empty page beyond the end', () => {
    renderFooter({ page: 2, perPage: 20, total: 40 });

    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  test('an empty result offers no navigation at all', () => {
    renderFooter({ page: 1, perPage: 20, total: 0 });

    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });
});
