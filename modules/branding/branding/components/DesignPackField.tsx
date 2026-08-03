import { keys, useT } from '@simple-module-py/i18n';
import { Label } from '@simple-module-py/ui/components/ui/label';

export interface DesignPackOption {
  value: string;
  label: string;
}

/**
 * `keys` is generated from every installed module's locale files and shipped
 * with the i18n package, so a host running the *released* package has no entry
 * for a key added here until that package is republished — and `t(undefined)`
 * renders an empty label rather than failing.
 *
 * Falling back to the literal path keeps the field readable in the meantime:
 * i18next resolves it against the locale JSON the backend serves, which is
 * already up to date. Drop the fallbacks once the package ships these keys.
 */
const K = keys as unknown as { branding?: { manage?: Record<string, string> } };
const LABEL_KEY = K.branding?.manage?.design_pack_label ?? 'branding.manage.design_pack_label';
const HELP_KEY = K.branding?.manage?.design_pack_help ?? 'branding.manage.design_pack_help';
const NONE_KEY = K.branding?.manage?.design_pack_none ?? 'branding.manage.design_pack_none';

/**
 * Picks the site's design pack.
 *
 * The options are the packs installed modules registered with the framework's
 * DesignPackRegistry — that list can't ride the shared `branding` prop, which
 * only carries the current selection, so the view supplies it as a page prop.
 *
 * Renders nothing when no module provides a pack: a dropdown whose only entry
 * is "None" is noise.
 */
export function DesignPackField({
  options,
  value,
  onChange,
  disabled,
}: {
  options: DesignPackOption[];
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  const { t } = useT();
  if (options.length === 0) return null;
  return (
    <div className="space-y-2">
      <Label htmlFor="design_pack">{t(LABEL_KEY)}</Label>
      {/* A native select rather than the shadcn one: this page imports no
          Select today, and the option list is short and static. */}
      <select
        id="design_pack"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full max-w-80 rounded-md border bg-transparent px-3 text-sm"
      >
        <option value="">{t(NONE_KEY)}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <p className="text-xs text-muted-foreground">{t(HELP_KEY)}</p>
    </div>
  );
}
