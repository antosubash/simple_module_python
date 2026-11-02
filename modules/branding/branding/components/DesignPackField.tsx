import { keys, useT } from '@simple-module-py/i18n';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
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

/**
 * The design pack, as one muted line in the form's foot.
 *
 * It was a full labelled field mid-form, which gave equal billing to a setting
 * most deployments never touch — and pushed the colour and logo controls, the
 * ones this page exists for, below the fold.
 */
export function DesignPackField({ options, value, onChange, disabled }: DesignPackFieldProps) {
  const { t } = useT();
  const none = t(keys.branding.manage.design_pack_none);

  if (options.length === 0) {
    return (
      <span className="text-[12.5px] text-muted-foreground">
        {t(keys.branding.manage.design_pack_empty)}
      </span>
    );
  }

  const current = options.find((pack) => pack.value === value);
  return (
    <Select
      value={value === '' ? NONE : value}
      disabled={disabled}
      onValueChange={(next) => onChange(next === NONE ? '' : next)}
    >
      <SelectTrigger
        id="design_pack"
        aria-label={t(keys.branding.manage.design_pack_label)}
        className="h-auto w-auto gap-1.5 border-0 bg-transparent p-0 text-[12.5px] font-medium text-muted-foreground shadow-none focus:ring-0"
      >
        {t(keys.branding.manage.design_pack_inline, { name: current?.label ?? none })}
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{none}</SelectItem>
        {options.map((pack) => (
          <SelectItem key={pack.value} value={pack.value}>
            {pack.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
