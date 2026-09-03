import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { X } from 'lucide-react';
import { useState } from 'react';
import type { FooterLink } from './dirty';

/** Mirrors `MAX_FOOTER_LINKS` in `branding/constants.py`. */
export const MAX_FOOTER_LINKS = 6;
/** Mirrors `MAX_FOOTER_LINK_LABEL_LEN`. */
export const MAX_FOOTER_LABEL = 40;
/** Mirrors `MAX_FOOTER_LINK_HREF_LEN`. */
export const MAX_FOOTER_HREF = 500;

interface FooterLinksFieldProps {
  links: FooterLink[];
  onChange: (next: FooterLink[]) => void;
  disabled: boolean;
}

/**
 * The site footer's links, as chips.
 *
 * Two inputs per row made a five-link footer a wall of text boxes for
 * something that is read as a single line. A finished link is a chip; only the
 * one being added shows fields — and it can't be added blank, which is what
 * the old "add an empty row" affordance produced.
 *
 * An empty list means "show the framework's own links", so removing the last
 * chip reads as a reset rather than an empty footer.
 */
export function FooterLinksField({ links, onChange, disabled }: FooterLinksFieldProps) {
  const { t } = useT();
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<FooterLink>({ label: '', href: '' });

  const complete = draft.label.trim() !== '' && draft.href.trim() !== '';
  const full = links.length >= MAX_FOOTER_LINKS;

  function commit() {
    if (!complete) return;
    onChange([...links, { label: draft.label.trim(), href: draft.href.trim() }]);
    setDraft({ label: '', href: '' });
    setAdding(false);
  }

  return (
    <div className="flex flex-col gap-2">
      <Label className="text-[12.5px] font-medium text-muted-foreground">
        {t(keys.branding.manage.footer_links_label)}
      </Label>

      <div className="flex flex-wrap items-center gap-2">
        {links.map((link, index) => (
          <span
            // Index-keyed on purpose: rows have no id and nothing enforces href
            // uniqueness, so a value-derived key would collide on duplicates.
            // biome-ignore lint/suspicious/noArrayIndexKey: see above
            key={index}
            className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 text-[12.5px]"
          >
            <span className="max-w-60 truncate">
              {link.label} · {link.href}
            </span>
            <button
              type="button"
              disabled={disabled}
              aria-label={t(keys.branding.manage.remove_button)}
              onClick={() => onChange(links.filter((_, i) => i !== index))}
              className="text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
            >
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          </span>
        ))}

        {!adding && (
          <button
            type="button"
            disabled={disabled || full}
            onClick={() => setAdding(true)}
            className="text-[12.5px] font-medium text-primary-700 transition-colors hover:text-primary-800 disabled:opacity-50 max-lg:min-h-11"
          >
            {t(keys.branding.manage.footer_links_add)}
          </button>
        )}
      </div>

      {adding && (
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={draft.label}
            maxLength={MAX_FOOTER_LABEL}
            disabled={disabled}
            aria-label={t(keys.branding.manage.footer_link_label_label)}
            placeholder={t(keys.branding.manage.footer_link_label_placeholder)}
            onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            className="w-36"
          />
          <Input
            value={draft.href}
            maxLength={MAX_FOOTER_HREF}
            disabled={disabled}
            aria-label={t(keys.branding.manage.footer_link_href_label)}
            placeholder={t(keys.branding.manage.footer_link_href_placeholder)}
            onChange={(e) => setDraft({ ...draft, href: e.target.value })}
            className="min-w-48 flex-1 font-mono text-xs"
          />
          <Button
            type="button"
            size="sm"
            className="max-lg:min-h-11"
            disabled={disabled || !complete}
            onClick={commit}
          >
            {t(keys.branding.manage.footer_link_add_confirm)}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="max-lg:min-h-11"
            onClick={() => setAdding(false)}
          >
            {t(keys.branding.manage.footer_link_add_cancel)}
          </Button>
        </div>
      )}
    </div>
  );
}
