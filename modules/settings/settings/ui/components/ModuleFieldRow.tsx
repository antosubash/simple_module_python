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
 * Three columns when the editor card has room, because the trailing column is
 * what makes the screen readable at a glance — every row answers "where is
 * this value from?" in the same place, so the exceptions stand out. The tracks
 * follow the card's width (container query), not the viewport: two sidebars
 * can leave a narrow card on a wide screen, and the row stacks instead.
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
    // Query the editor card: two sidebars can leave little space at a wide viewport.
    <div className="grid grid-cols-1 gap-3 @md:grid-cols-[minmax(0,140px)_minmax(180px,1fr)] @xl:grid-cols-[minmax(0,140px)_minmax(180px,1fr)_minmax(0,160px)] @xl:items-center">
      <div className="min-w-0">
        <label htmlFor={id} className="block [overflow-wrap:anywhere] text-[13px] font-medium">
          {field.name}
        </label>
        {showDescription && (
          <p className="mt-0.5 [overflow-wrap:anywhere] text-[11.5px] leading-snug text-muted-foreground">
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
        {/* An env-set field always wins over a stored value (env → DB → default),
            so the server refuses edits to it; a disabled fieldset stops the form
            from collecting an edit that would 422 the whole save. */}
        <fieldset disabled={!!field.env_set} className="min-w-0 border-0 p-0">
          <FieldInput id={id} field={field} value={value} onChange={onChange} />
        </fieldset>
      </div>

      <div className="min-w-0 [overflow-wrap:anywhere] @md:col-span-2 @xl:col-span-1 @xl:justify-self-start">
        <FieldSource field={field} onReset={onReset} />
      </div>

      {/* Its own grid row, spanning the control and trailing columns: inside
          the control's cell it shared that cell with the input and wrapped a
          word per line whenever the cell was narrow. */}
      {error && (
        <p
          data-testid={`field-error-${field.name}`}
          className="min-w-0 [overflow-wrap:anywhere] text-xs text-destructive @md:col-span-1 @md:col-start-2 @xl:col-span-2"
        >
          {error}
        </p>
      )}
    </div>
  );
}
