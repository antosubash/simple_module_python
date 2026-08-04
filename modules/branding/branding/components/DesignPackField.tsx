import { keys, useT } from '@simple-module-py/i18n';
import { Label } from '@simple-module-py/ui/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';

export interface DesignPackOption {
  value: string;
  label: string;
}

/** Sentinel for "no pack" — Radix Select forbids an empty-string item value. */
const NONE = '__none__';

interface DesignPackFieldProps {
  /** Packs the installed modules registered. Empty means nothing to choose. */
  options: DesignPackOption[];
  /** Currently selected slug; '' for base tokens only. */
  value: string;
  onChange: (next: string) => void;
  disabled: boolean;
}

export function DesignPackField({ options, value, onChange, disabled }: DesignPackFieldProps) {
  const { t } = useT();

  return (
    <div className="space-y-2">
      <Label htmlFor="design_pack">{t(keys.branding.manage.design_pack_label)}</Label>
      <Select
        value={value === '' ? NONE : value}
        disabled={disabled || options.length === 0}
        onValueChange={(next) => onChange(next === NONE ? '' : next)}
      >
        <SelectTrigger id="design_pack" className="max-w-72">
          <SelectValue placeholder={t(keys.branding.manage.design_pack_none)} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>{t(keys.branding.manage.design_pack_none)}</SelectItem>
          {options.map((pack) => (
            <SelectItem key={pack.value} value={pack.value}>
              {pack.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-xs text-muted-foreground">
        {options.length === 0
          ? t(keys.branding.manage.design_pack_empty)
          : t(keys.branding.manage.design_pack_help)}
      </p>
    </div>
  );
}
