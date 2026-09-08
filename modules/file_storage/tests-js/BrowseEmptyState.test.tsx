/**
 * `showEmpty` — when the table says "nothing here", and which "nothing".
 *
 * Two decisions are encoded in one line and its neighbours, and neither is
 * obvious enough to leave unpinned:
 *
 * - `total === 0`, not `files.length === 0`. `total` is filter-aware, so a page
 *   past the last one renders an empty `files` array while the bucket is full;
 *   keying on the array would announce "No files yet" over a full bucket.
 * - The copy splits on whether a filter is active. "No files yet" is wrong, and
 *   discouraging, when the bucket is full and the filter is merely too narrow.
 */
import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'file_storage.browse.head_title': 'Files',
    'file_storage.browse.title': 'Files',
    'file_storage.browse.subtitle': '{backend} · {used} used · {max} per file',
    'file_storage.browse.subtitle_empty': '{backend} · nothing uploaded yet',
    'file_storage.browse.empty_title': 'No files yet',
    'file_storage.browse.empty_description': 'Upload something to get started.',
    'file_storage.browse.no_match_title': 'No matching files',
    'file_storage.browse.no_match_description': 'Nothing matches this filter.',
    'file_storage.browse.clear_filters': 'Clear filters',
    'file_storage.browse.showing': 'Showing {from}–{to} of {total}',
    'file_storage.browse.selected_showing': '{count} selected · showing {from}–{to} of {total}',
    'file_storage.browse.previous': 'Previous',
    'file_storage.browse.next': 'Next',
  },
});

let pageProps: Record<string, unknown> = {};

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  router: { get: vi.fn(), reload: vi.fn(), delete: vi.fn() },
  usePage: () => ({ props: pageProps }),
}));

vi.mock('@simple-module-py/ui/hooks/use-permissions', () => ({
  usePermissions: () => ({ can: () => true }),
}));

vi.mock('@simple-module-py/ui/layouts/AuthenticatedLayout', () => ({
  AuthenticatedLayout: ({ children }: { children?: unknown }) => <>{children as never}</>,
}));

const { default: Browse } = await import('../file_storage/pages/Browse');

const BASE = {
  files: [],
  pagination: { page: 1, perPage: 20, total: 0 },
  content_types: [],
  uploaders: [],
  backend: 'filesystem',
  used_bytes: 0,
  max_upload_bytes: 10_485_760,
  filters: { q: '', content_type: '', uploaded_by: '' },
};

function renderBrowse(overrides: Record<string, unknown> = {}) {
  pageProps = { ...BASE, ...overrides };
  render(<Browse />);
}

beforeEach(() => {
  pageProps = { ...BASE };
});

describe('an empty bucket', () => {
  test('it says so, and offers nothing to clear', () => {
    renderBrowse();

    expect(screen.getByText('No files yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument();
  });
});

describe('a filter that matched nothing', () => {
  test('it does not claim the bucket is empty', () => {
    renderBrowse({ filters: { q: 'invoice', content_type: '', uploaded_by: '' } });

    expect(screen.getByText('No matching files')).toBeInTheDocument();
    expect(screen.queryByText('No files yet')).not.toBeInTheDocument();
  });

  test('it offers a way back out', () => {
    renderBrowse({ filters: { q: 'invoice', content_type: '', uploaded_by: '' } });

    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  });

  test('any one of the three filters counts as filtered', () => {
    renderBrowse({ filters: { q: '', content_type: 'image/png', uploaded_by: '' } });
    expect(screen.getByText('No matching files')).toBeInTheDocument();
  });
});

describe('a page past the end of a full bucket', () => {
  test('no empty state at all — the bucket is not empty', () => {
    // `files` is empty here but `total` is not, which is exactly the case
    // `files.length === 0` alone would get wrong.
    renderBrowse({ files: [], pagination: { page: 9, perPage: 20, total: 45 } });

    expect(screen.queryByText('No files yet')).not.toBeInTheDocument();
    expect(screen.queryByText('No matching files')).not.toBeInTheDocument();
  });
});

describe('the footer', () => {
  test('it is rendered even with nothing to page through', () => {
    renderBrowse();

    expect(screen.getByText('Showing 0–0 of 0')).toBeInTheDocument();
  });
});
