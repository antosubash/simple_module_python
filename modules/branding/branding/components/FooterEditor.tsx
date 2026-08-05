import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { type EditableLink, LinkRows, newRowId } from './LinkRows';

/** Mirror the server limits in `branding/footer.py`. */
export const MAX_COLUMNS = 6;
export const MAX_LINKS_PER_COLUMN = 8;
export const MAX_SOCIAL_LINKS = 8;

export interface EditableColumn {
  /** Client-only key; see LinkRows. Stripped before sending. */
  id: string;
  title: string;
  links: EditableLink[];
}

export interface FooterDraft {
  tagline: string;
  copyrightOwner: string;
  note: string;
  columns: EditableColumn[];
  socialLinks: EditableLink[];
}

export const EMPTY_FOOTER: FooterDraft = {
  tagline: '',
  copyrightOwner: '',
  note: '',
  columns: [],
  socialLinks: [],
};

interface FooterEditorProps {
  value: FooterDraft;
  onChange: (next: FooterDraft) => void;
  disabled: boolean;
}

/** Multi-column footer builder: brand text, link columns and a social row. */
export function FooterEditor({ value, onChange, disabled }: FooterEditorProps) {
  const { t } = useT();
  const patch = (next: Partial<FooterDraft>) => onChange({ ...value, ...next });

  const updateColumn = (id: string, next: Partial<EditableColumn>) =>
    patch({ columns: value.columns.map((c) => (c.id === id ? { ...c, ...next } : c)) });

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="footer_tagline">{t(keys.branding.manage.footer_tagline_label)}</Label>
          <Input
            id="footer_tagline"
            value={value.tagline}
            disabled={disabled}
            onChange={(e) => patch({ tagline: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="footer_copyright">{t(keys.branding.manage.footer_copyright_label)}</Label>
          <Input
            id="footer_copyright"
            value={value.copyrightOwner}
            disabled={disabled}
            onChange={(e) => patch({ copyrightOwner: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="footer_note">{t(keys.branding.manage.footer_note_label)}</Label>
          <Input
            id="footer_note"
            value={value.note}
            disabled={disabled}
            onChange={(e) => patch({ note: e.target.value })}
          />
        </div>
      </div>

      <div className="space-y-3">
        {value.columns.map((column, index) => (
          <div key={column.id} className="space-y-2 rounded-lg border p-3">
            <div className="flex items-center gap-2">
              <Input
                value={column.title}
                disabled={disabled}
                placeholder={t(keys.branding.manage.footer_column_title)}
                onChange={(e) => updateColumn(column.id, { title: e.target.value })}
                className="w-56 font-medium"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={disabled}
                aria-label={`${t(keys.branding.manage.footer_remove_column)}: ${column.title || index + 1}`}
                onClick={() => patch({ columns: value.columns.filter((c) => c.id !== column.id) })}
              >
                {t(keys.branding.manage.footer_remove_column)}
              </Button>
            </div>
            <LinkRows
              links={column.links}
              max={MAX_LINKS_PER_COLUMN}
              disabled={disabled}
              onChange={(links) => updateColumn(column.id, { links })}
            />
          </div>
        ))}
        {value.columns.length < MAX_COLUMNS && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={() =>
              patch({ columns: [...value.columns, { id: newRowId(), title: '', links: [] }] })
            }
          >
            {t(keys.branding.manage.footer_add_column)}
          </Button>
        )}
      </div>

      <div className="space-y-2">
        <Label>{t(keys.branding.manage.footer_social_label)}</Label>
        <LinkRows
          links={value.socialLinks}
          max={MAX_SOCIAL_LINKS}
          disabled={disabled}
          onChange={(socialLinks) => patch({ socialLinks })}
        />
      </div>

      <p className="text-xs text-muted-foreground">{t(keys.branding.manage.footer_help)}</p>
    </div>
  );
}
