import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@simple-module-py/ui/components/ui/card';
import type { FooterShared } from '@simple-module-py/ui/types';
import { useState } from 'react';
import { EMPTY_FOOTER, type FooterDraft, FooterEditor } from './FooterEditor';
import { newRowId, stripIds } from './LinkRows';

/** Payload shape of `PUT /api/branding/footer` (snake_case, like the DTO). */
export interface FooterPayload {
  tagline: string;
  copyright_owner: string;
  note: string;
  columns: { title: string; links: { label: string; href: string }[] }[];
  social_links: { label: string; href: string }[];
}

interface FooterCardProps {
  /** Current server-side footer, or null when none is configured. */
  initial: FooterShared | null;
  disabled: boolean;
  busy: boolean;
  onSave: (payload: FooterPayload) => void;
}

/** Rows get a client-only id so React keys stay stable across add/remove. */
function toDraft(footer: FooterShared | null): FooterDraft {
  if (!footer) return EMPTY_FOOTER;
  return {
    tagline: footer.tagline,
    copyrightOwner: footer.copyrightOwner,
    note: footer.note,
    columns: footer.columns.map((c) => ({
      id: newRowId(),
      title: c.title,
      links: c.links.map((l) => ({ id: newRowId(), ...l })),
    })),
    socialLinks: footer.socialLinks.map((l) => ({ id: newRowId(), ...l })),
  };
}

/**
 * The footer section of the branding page — its own card, its own draft state
 * and its own save, because a footer edit replaces the whole structure and is
 * independent of the identity fields above it.
 */
export function FooterCard({ initial, disabled, busy, onSave }: FooterCardProps) {
  const { t } = useT();
  const [draft, setDraft] = useState<FooterDraft>(() => toDraft(initial));

  const save = () =>
    onSave({
      tagline: draft.tagline,
      copyright_owner: draft.copyrightOwner,
      note: draft.note,
      columns: stripIds(draft.columns).map((c) => ({
        title: c.title,
        links: stripIds(c.links),
      })),
      social_links: stripIds(draft.socialLinks),
    });

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle>{t(keys.branding.manage.footer_title)}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <FooterEditor value={draft} onChange={setDraft} disabled={disabled} />
        <Button type="button" disabled={disabled} onClick={save}>
          {busy ? t(keys.branding.manage.saving) : t(keys.branding.manage.footer_save_button)}
        </Button>
      </CardContent>
    </Card>
  );
}
