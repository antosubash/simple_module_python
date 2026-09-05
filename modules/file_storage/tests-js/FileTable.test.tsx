import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'file_storage.table.select_all': 'Select every file on this page',
    'file_storage.table.select_row': 'Select {name}',
    'file_storage.table.filename': 'File',
    'file_storage.table.type': 'Type',
    'file_storage.table.size': 'Size',
    'file_storage.table.uploaded_by': 'Uploaded by',
    'file_storage.table.when': 'When',
    'file_storage.table.actions': 'Actions',
    'file_storage.actions.download': 'Download',
  },
});

import { FileTable } from '../file_storage/pages/components/FileTable';
import type { StoredFile } from '../file_storage/pages/types';

const FILES: StoredFile[] = [
  {
    id: 'f1',
    filename: 'quarterly.pdf',
    content_type: 'application/pdf',
    size_bytes: 2048,
    uploaded_by_label: 'admin',
    created_at: '2026-09-03T10:00:00Z',
  } as StoredFile,
];

function renderTable(selectedIds: string[] = []) {
  return render(
    <FileTable
      files={FILES}
      selectedIds={selectedIds}
      canDelete
      onToggleRow={vi.fn()}
      onToggleAll={vi.fn()}
      empty={null}
    />,
  );
}

describe('FileTable selection checkboxes', () => {
  test('both checkboxes are named for a screen reader', () => {
    renderTable();

    expect(
      screen.getByRole('checkbox', { name: 'Select every file on this page' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /quarterly\.pdf/ })).toBeInTheDocument();
  });

  test('both checkboxes carry the 44px phone bleed', () => {
    renderTable();

    for (const name of ['Select every file on this page', /quarterly\.pdf/] as const) {
      expect(screen.getByRole('checkbox', { name })).toHaveClass('max-lg:before:-inset-3.5');
    }
  });

  test('the header row is tall enough on phones to hold that bleed', () => {
    renderTable();

    // The 14px above the select-all box has nowhere to go otherwise: the
    // table container is `overflow-x-auto` inside an `overflow-hidden` card,
    // and a clipped overflow region is not hit-testable. A 56px header row
    // centres the 16px box with 20px of cell either side, so the whole target
    // stays inside.
    const cell = screen
      .getByRole('checkbox', { name: 'Select every file on this page' })
      .closest('th');

    expect(cell).toHaveClass('max-lg:h-14');
  });

  test('the header reports the all-selected state', () => {
    renderTable(['f1']);

    expect(screen.getByRole('checkbox', { name: 'Select every file on this page' })).toBeChecked();
  });
});
