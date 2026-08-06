import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';

/**
 * Rows carry a client-only `id`. Keying on the array index instead would make
 * React reuse the wrong DOM node when a middle row is removed — the inputs
 * below the gap keep the deleted row's text. The id never leaves the browser;
 * `stripIds` drops it before the payload is sent.
 */
export interface EditableLink {
  id: string;
  label: string;
  href: string;
}

let nextRowId = 0;

/** Stable key for a newly added row. Not persisted, so a counter is enough. */
export function newRowId(): string {
  nextRowId += 1;
  return `row-${nextRowId}`;
}

export function stripIds<T extends { id: string }>(rows: T[]): Omit<T, 'id'>[] {
  return rows.map(({ id: _id, ...rest }) => rest);
}

interface LinkRowsProps {
  links: EditableLink[];
  max: number;
  disabled: boolean;
  onChange: (next: EditableLink[]) => void;
}

/**
 * Repeating label + URL rows with add/remove. Shared by the column editor and
 * the social row, which differ only in where their list is stored.
 *
 * No drag-reorder: order is edit order, and the server stores the array as
 * given. Adding one would need a DnD dependency for a list capped at 8.
 */
export function LinkRows({ links, max, disabled, onChange }: LinkRowsProps) {
  const { t } = useT();

  const update = (id: string, patch: Partial<EditableLink>) =>
    onChange(links.map((link) => (link.id === id ? { ...link, ...patch } : link)));

  return (
    <div className="space-y-2">
      {links.map((link, index) => (
        <div key={link.id} className="flex flex-wrap items-center gap-2">
          <Input
            value={link.label}
            disabled={disabled}
            placeholder={t(keys.branding.manage.footer_link_label)}
            onChange={(e) => update(link.id, { label: e.target.value })}
            className="w-40"
          />
          <Input
            value={link.href}
            disabled={disabled}
            placeholder={t(keys.branding.manage.footer_link_href)}
            onChange={(e) => update(link.id, { href: e.target.value })}
            className="min-w-52 flex-1 font-mono text-xs"
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            aria-label={`${t(keys.branding.manage.footer_remove_link)}: ${link.label || index + 1}`}
            onClick={() => onChange(links.filter((row) => row.id !== link.id))}
          >
            {t(keys.branding.manage.footer_remove_link)}
          </Button>
        </div>
      ))}
      {links.length < max && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => onChange([...links, { id: newRowId(), label: '', href: '' }])}
        >
          {t(keys.branding.manage.footer_add_link)}
        </Button>
      )}
    </div>
  );
}
