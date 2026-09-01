import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';

/** Mirrors `MAX_FOOTER_LINKS` in `branding/constants.py`. */
export const MAX_FOOTER_LINKS = 6;
/** Mirrors `MAX_FOOTER_LINK_LABEL_LEN`. */
export const MAX_FOOTER_LABEL = 40;
/** Mirrors `MAX_FOOTER_LINK_HREF_LEN`. */
export const MAX_FOOTER_HREF = 500;

export interface FooterLink {
  label: string;
  href: string;
}

interface FooterLinksFieldProps {
  links: FooterLink[];
  onChange: (next: FooterLink[]) => void;
  disabled: boolean;
}

/**
 * Editor for the links in the site footer.
 *
 * An empty list means "show the framework's own links", which is why removing
 * the last row is allowed and reads as a reset rather than an empty footer.
 * The server enforces the same caps and an href allow-list; the `maxLength`
 * attributes here just stop the round trip.
 */
export function FooterLinksField({ links, onChange, disabled }: FooterLinksFieldProps) {
  const { t } = useT();

  const update = (index: number, patch: Partial<FooterLink>) =>
    onChange(links.map((link, i) => (i === index ? { ...link, ...patch } : link)));

  const remove = (index: number) => onChange(links.filter((_, i) => i !== index));

  const add = () => onChange([...links, { label: '', href: '' }]);

  return (
    <div className="space-y-2">
      <Label>{t(keys.branding.manage.footer_links_label)}</Label>

      {links.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {t(keys.branding.manage.footer_links_empty)}
        </p>
      ) : (
        <ul className="space-y-2">
          {links.map((link, index) => (
            // Index-keyed on purpose: rows have no id, and label/href are the
            // very fields being edited, so a value-derived key would remount
            // the input on every keystroke and lose focus.
            // biome-ignore lint/suspicious/noArrayIndexKey: see above
            <li key={index} className="flex flex-wrap items-center gap-2">
              <Input
                value={link.label}
                maxLength={MAX_FOOTER_LABEL}
                disabled={disabled}
                aria-label={t(keys.branding.manage.footer_link_label_label)}
                placeholder={t(keys.branding.manage.footer_link_label_placeholder)}
                onChange={(e) => update(index, { label: e.target.value })}
                className="w-40"
              />
              <Input
                value={link.href}
                maxLength={MAX_FOOTER_HREF}
                disabled={disabled}
                aria-label={t(keys.branding.manage.footer_link_href_label)}
                placeholder={t(keys.branding.manage.footer_link_href_placeholder)}
                onChange={(e) => update(index, { href: e.target.value })}
                className="min-w-60 flex-1 font-mono text-xs"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={disabled}
                onClick={() => remove(index)}
              >
                {t(keys.branding.manage.remove_button)}
              </Button>
            </li>
          ))}
        </ul>
      )}

      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled || links.length >= MAX_FOOTER_LINKS}
        onClick={add}
      >
        {t(keys.branding.manage.footer_links_add)}
      </Button>

      <p className="text-xs text-muted-foreground">{t(keys.branding.manage.footer_links_help)}</p>
    </div>
  );
}
