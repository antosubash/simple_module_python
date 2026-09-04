import { keys, useT } from '@simple-module-py/i18n';
import { FieldInput, type FieldMeta } from './FieldInput';
import { FieldSource } from './FieldSource';

interface Props {
  field: FieldMeta;
  package: string;
  value: unknown;
  /** Dirty relative to the saved baseline, not to the default. */
  modified: boolean;
  error?: string;
  onChange: (name: string, value: unknown) => void;
  onReset: () => void;
}

/**
 * One settings row: label, control, trailing meta.
 *
 * Three columns rather than a stacked label block, because the trailing column
 * is what makes the screen readable at a glance — every row answers "where is
 * this value from?" in the same place, so the exceptions stand out instead of
 * having to be hunted for.
 */
export function ModuleFieldRow({
  field,
  package: pkg,
  value,
  modified,
  error,
  onChange,
  onReset,
}: Props) {
  const { t } = useT();
  const id = `field-${pkg}-${field.name}`;
  // A bool's description is the trailing meta; repeating it here would print
  // the same sentence twice on the same row.
  const showDescription = field.description && field.type !== 'bool';

  return (
    // `minmax(170px, auto)`: a fixed 170px track cannot grow, so a long field
    // name overflowed it and printed straight over the input beside it.
    <div className="grid gap-3 sm:grid-cols-[minmax(170px,auto)_1fr] lg:grid-cols-[minmax(170px,auto)_1fr_210px] lg:items-center">
      <div className="min-w-0">
        <label htmlFor={id} className="block break-words text-[13px] font-medium">
          {field.name}
        </label>
        {showDescription && (
          <p className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">
            {field.description}
          </p>
        )}
        {field.requires_restart && modified && (
          <span className="mt-1 inline-block rounded bg-amber-50 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-amber-700">
            {t(keys.settings.modules_form.requires_restart)}
          </span>
        )}
      </div>

      <div className="min-w-0">
        <FieldInput id={id} field={field} value={value} onChange={onChange} />
        {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
      </div>

      <div className="sm:col-span-2 lg:col-span-1 lg:justify-self-start">
        <FieldSource field={field} onReset={onReset} />
      </div>
    </div>
  );
}
