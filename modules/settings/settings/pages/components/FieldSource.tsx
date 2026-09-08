import { keys, useT } from '@simple-module-py/i18n';
import type { FieldMeta } from './FieldInput';

function isBlank(value: unknown): boolean {
  return value === null || value === undefined || value === '';
}

/**
 * The trailing column of a settings row: where this value came from, and the
 * one action that applies to it.
 *
 * Without this, a field whose `SM_*` env var is set in the deployment looks
 * identical to one running on its default, and a stored override that is
 * quietly shadowing the env var looks like nothing at all. Both produce the
 * same support question — "I changed the setting and nothing happened" —
 * which this answers on the screen.
 */
export function FieldSource({ field, onReset }: { field: FieldMeta; onReset: () => void }) {
  const { t } = useT();

  // Revert is gated on `db_override`, not on "differs from the default": a
  // field reading an env var that differs from its default has no stored row
  // to delete, and a stored override that happens to equal the default is
  // still an override someone has to be able to remove.
  if (field.db_override) {
    return (
      <span className="text-[11.5px] font-medium text-primary-700">
        {field.env_set
          ? t(keys.settings.modules.source_db_over_env)
          : t(keys.settings.modules.source_db)}
        <span aria-hidden="true"> · </span>
        <button type="button" onClick={onReset} className="font-medium hover:underline">
          {t(keys.settings.modules_form.reset_to_default)}
        </button>
      </span>
    );
  }

  if (field.is_secret) {
    return (
      <span className="text-[11.5px] text-muted-foreground">
        {t(keys.settings.modules.secret_write_only)}
      </span>
    );
  }

  // A toggle's env var name says nothing a reader wants; what the switch
  // currently means does.
  if (field.type === 'bool' && field.description) {
    return <span className="text-[11.5px] text-muted-foreground">{field.description}</span>;
  }

  // The default is only worth showing when the live value has moved away from
  // it — otherwise the row repeats the control next to it.
  const showDefault = !isBlank(field.default) && String(field.default) !== String(field.value);
  return (
    // Wraps rather than clips: `SM_FILE_STORAGE_QUOTA_BYTES` has no space to
    // break at, so a 210px column cut it mid-word with nothing to say so.
    // `break-words` breaks only the tokens that do not fit.
    <span
      className="block break-words font-mono text-[11.5px] leading-snug text-muted-foreground"
      title={
        field.env_readable
          ? t(keys.settings.modules.env_var_hint)
          : t(keys.settings.modules.env_var_not_read_hint, { env_var: field.env_var })
      }
    >
      {field.env_var}
      {showDefault && (
        <>
          <span aria-hidden="true"> · </span>
          {String(field.default)}
        </>
      )}
    </span>
  );
}
