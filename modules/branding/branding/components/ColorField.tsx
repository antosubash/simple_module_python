import { keys, useT } from '@simple-module-py/i18n';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { isValidColor, normalizeHex } from './hex';

interface ColorFieldProps {
  value: string;
  /** Shown in the swatch and as placeholder while the value is empty or invalid. */
  fallback: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}

/** Native swatch plus a hex textbox that flags — and normalises — what is typed. */
export function ColorField({ value, fallback, disabled, onChange }: ColorFieldProps) {
  const { t } = useT();
  const valid = isValidColor(value);
  const label = t(keys.branding.manage.primary_color_label);
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor="primary_color" className="text-[12.5px] font-medium text-muted-foreground">
        {label}
      </Label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          aria-label={label}
          value={normalizeHex(value) ?? fallback}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="h-9 w-9 shrink-0 cursor-pointer rounded-[9px] border bg-transparent"
        />
        <Input
          id="primary_color"
          value={value}
          placeholder={fallback}
          disabled={disabled}
          aria-invalid={!valid}
          aria-describedby={valid ? undefined : 'primary_color_error'}
          onChange={(e) => onChange(e.target.value)}
          onBlur={() => {
            const normal = normalizeHex(value);
            if (normal && normal !== value) onChange(normal);
          }}
          className="min-w-0 flex-1 font-mono"
        />
      </div>
      {valid ? null : (
        <p id="primary_color_error" role="alert" className="text-xs text-destructive">
          {t(keys.branding.manage.primary_color_invalid)}
        </p>
      )}
    </div>
  );
}
