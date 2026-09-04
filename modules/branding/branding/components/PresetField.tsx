import { keys, useT } from '@simple-module-py/i18n';
import { Label } from '@simple-module-py/ui/components/ui/label';

export interface PresetOption {
  key: string;
  label: string;
  /** Primary colour the preset applies, when it sets one. */
  swatch: string | null;
}

interface PresetFieldProps {
  options: PresetOption[];
  /** Colour currently in the form, used to mark the active chip. */
  activeColor: string;
  /** Stages the colour locally — nothing reaches the server until Publish. */
  onSelect: (swatch: string) => void;
  disabled: boolean;
}

/**
 * One-click looks, staged like every other field on this form.
 *
 * Applying used to POST immediately, which made the header's "unsaved changes"
 * count a lie: the page said nothing was pending while the site had already
 * changed colour for everyone. A preset is now just a fast way to fill in the
 * colour field.
 */
export function PresetField({ options, activeColor, onSelect, disabled }: PresetFieldProps) {
  const { t } = useT();
  if (options.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <Label className="text-[12.5px] font-medium text-muted-foreground">
        {t(keys.branding.manage.preset_label)}
      </Label>
      <div className="flex flex-wrap gap-2">
        {options.map((preset) => {
          const active =
            preset.swatch !== null && preset.swatch.toLowerCase() === activeColor.toLowerCase();
          return (
            <button
              key={preset.key}
              type="button"
              disabled={disabled || preset.swatch === null}
              onClick={() => preset.swatch && onSelect(preset.swatch)}
              aria-pressed={active}
              className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition-colors disabled:opacity-50 max-lg:min-h-11 ${
                active
                  ? 'border-primary bg-primary-600/10 text-primary-700'
                  : 'border-border text-muted-foreground hover:bg-secondary/60'
              }`}
            >
              {preset.swatch && (
                <span
                  aria-hidden="true"
                  className="h-3 w-3 rounded-full border border-black/10"
                  style={{ backgroundColor: preset.swatch }}
                />
              )}
              {preset.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
