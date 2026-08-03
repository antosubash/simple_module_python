import { keys, useT } from '@simple-module-py/i18n';
import { Label } from '@simple-module-py/ui/components/ui/label';

export interface DesignPackOption {
  value: string;
  label: string;
}

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
      <Label htmlFor="design_pack">{t(keys.branding.manage.design_pack_label)}</Label>
      {/* A native select rather than the shadcn one: this page imports no
          Select today, and the option list is short and static. */}
      <select
        id="design_pack"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full max-w-80 rounded-md border bg-transparent px-3 text-sm"
      >
        <option value="">{t(keys.branding.manage.design_pack_none)}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <p className="text-xs text-muted-foreground">{t(keys.branding.manage.design_pack_help)}</p>
    </div>
  );
}
