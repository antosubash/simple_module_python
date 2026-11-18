import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import de from '../sharing/locales/de.json';
import en from '../sharing/locales/en.json';
import { ShareDialog } from '../sharing/ui';

afterEach(() => vi.unstubAllGlobals());

it.each([
  ['en', en, 'Share', 'Type at least 3 characters to search.', 'Remove access for Ada'],
  ['de', de, 'Freigeben', 'Geben Sie mindestens 3 Zeichen ein.', 'Zugriff für Ada entfernen'],
] as const)(
  'interpolates real %s guidance and accessible recipient labels',
  async (locale, catalog, button, guidance, remove) => {
    configureI18n({
      locale,
      messages: Object.fromEntries(
        Object.entries(catalog.dialog).map(([key, value]) => [`sharing.dialog.${key}`, value]),
      ),
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json([
          {
            id: 'share',
            resource_type: 'notes.note',
            resource_id: 'note',
            subject_type: 'user',
            subject_id: 'ada',
            subject_label: 'Ada',
            role: 'view',
            granted_by: 'owner',
            granted_by_label: null,
            expires_at: null,
            expired: false,
            created_at: null,
          },
        ]),
      ),
    );
    render(<ShareDialog resourceType="notes.note" resourceId="note" />);
    fireEvent.click(screen.getByRole('button', { name: button }));
    expect(await screen.findByText(guidance)).toBeVisible();
    expect(await screen.findByRole('button', { name: remove })).toBeVisible();
  },
);
