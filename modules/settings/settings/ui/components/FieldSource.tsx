import { keys, type TranslationKey, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { cn } from '@simple-module-py/ui/lib/utils';
import type { FieldMeta } from './FieldInput';

function isBlank(value: unknown): boolean {
  return value === null || value === undefined || value === '';
}

function display(value: unknown): string {
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}

type Tone = 'neutral' | 'primary' | 'amber';

const TONES: Record<Tone, string> = {
  neutral: 'bg-muted text-muted-foreground',
  primary: 'bg-primary-600/10 text-primary-700 dark:text-primary-300',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300',
};

/** First match wins: an unsaved edit, then env (which beats a stored row), then the stored row. */
function source(field: FieldMeta, modified: boolean): [Tone, TranslationKey] {
  const m = keys.settings.modules;
  if (modified) return ['amber', m.source_unsaved];
  if (field.env_set)
    return ['amber', field.db_override ? m.source_db_ignored_for_env : m.source_env];
  if (field.db_override) return ['primary', m.source_db];
  return ['neutral', field.is_secret ? m.secret_write_only : m.source_default];
}

/**
 * The line under a settings control: where the value comes from, the default
 * once the value has moved away from it, and Reset when a stored row exists.
 *
 * Without it a field whose env var is set looks identical to one on its
 * default, and a stored override that env quietly overrules (env → DB →
 * default) looks like nothing at all — the "I changed it and nothing
 * happened" support question this answers on screen. The `SM_*` name appears
 * only when the environment really supplies the value; for DB-only modules it
 * is a label nobody can act on.
 */
export function FieldSource({
  field,
  label,
  value,
  modified,
  onReset,
}: {
  field: FieldMeta;
  /** The field's display label, for the Reset button's accessible name. */
  label: string;
  /** The current draft value. */
  value: unknown;
  modified: boolean;
  onReset: () => void;
}) {
  const { t } = useT();

  const [tone, sourceKey] = source(field, modified);

  // The default is worth showing only once the value has moved away from it;
  // otherwise it repeats the control above. A secret's default stays hidden.
  const showDefault =
    !field.is_secret && !isBlank(field.default) && display(field.default) !== display(value);

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      <Badge variant="secondary" className={cn('font-semibold', TONES[tone])}>
        {t(sourceKey)}
      </Badge>
      {field.env_source_var && (
        <code
          className="min-w-0 [overflow-wrap:anywhere] font-mono text-[11px] text-muted-foreground"
          title={t(keys.settings.modules.env_var_hint)}
        >
          {field.env_source_var}
        </code>
      )}
      {showDefault && (
        <span className="min-w-0 [overflow-wrap:anywhere] text-muted-foreground">
          {t(keys.settings.modules.default_value, { value: display(field.default) })}
        </span>
      )}
      {/* Gated on `db_override`, not "differs from the default": an env value
          has no stored row to delete, and a stored override equal to the
          default is still an override someone must be able to remove. */}
      {field.db_override && (
        <button
          type="button"
          onClick={onReset}
          aria-label={t(keys.settings.modules_form.revert_field, { field: label })}
          className="ml-auto font-semibold text-primary-700 hover:underline dark:text-primary-300 max-lg:min-h-11 pointer-coarse:min-h-11"
        >
          {t(keys.settings.modules_form.reset_to_default)}
        </button>
      )}
    </div>
  );
}
