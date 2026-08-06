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
  /** Currently applied primary colour, used to mark the active swatch. */
  activeColor: string;
  onApply: (key: string) => void;
  disabled: boolean;
}

/**
 * One-click looks. Applying is a direct server action rather than a staged
 * edit: a preset is a *jump* to a known-good look, so pretending it is pending
 * local state would misrepresent what the button does.
 */
export function PresetField({ options, activeColor, onApply, disabled }: PresetFieldProps) {
  const { t } = useT();
  if (options.length === 0) return null;

  return (
    <div className="space-y-2">
      <Label>{t(keys.branding.manage.preset_label)}</Label>
      <div className="flex flex-wrap gap-2">
        {options.map((preset) => {
          const isActive =
            preset.swatch !== null && preset.swatch.toLowerCase() === activeColor.toLowerCase();
          return (
            <button
              key={preset.key}
              type="button"
              disabled={disabled}
              onClick={() => onApply(preset.key)}
              aria-pressed={isActive}
              className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                isActive ? 'border-foreground bg-secondary' : 'border-border hover:bg-secondary/60'
              }`}
            >
              {preset.swatch && (
                <span
                  aria-hidden="true"
                  className="h-3.5 w-3.5 rounded-full border border-black/10"
                  style={{ backgroundColor: preset.swatch }}
                />
              )}
              {preset.label}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">{t(keys.branding.manage.preset_help)}</p>
    </div>
  );
}
