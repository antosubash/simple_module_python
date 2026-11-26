import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { FileFilterBar } from '../file_storage/ui/components/FileFilterBar';

test('file search has a narrow/coarse touch target (#1184)', () => {
  configureI18n({
    locale: 'en',
    messages: { 'file_storage.filters.search_placeholder': 'Search files' },
  });
  render(
    <FileFilterBar
      filters={{ q: '', content_type: '', uploaded_by: '' }}
      facets={[]}
      uploaders={[]}
      onChange={() => {}}
    />,
  );
  expect(screen.getByRole('textbox', { name: 'Search files' })).toHaveClass(
    'max-lg:min-h-11',
    'pointer-coarse:min-h-11',
  );
});
