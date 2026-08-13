import { keys, useT } from '@simple-module-py/i18n';
import type { FieldMeta } from './FieldInput';

/**
 * Where a field's live value came from, and what the env var behind it is.
 *
 * Without this, a field whose `SM_*` env var is set in the deployment looks
 * identical to one running on its default, and a stored override that is
 * quietly shadowing the env var looks like nothing at all. Both produce the
 * same support question — "I changed the setting and nothing happened" —
 * which this answers on the screen.
 */
export function FieldSource({ field }: { field: FieldMeta }) {
  const { t } = useT();
  const source = field.source ?? 'default';

  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5">
      <code
        className="rounded bg-secondary px-1 py-0.5 font-mono text-[10px] text-muted-foreground"
        title={t(keys.settings.modules.env_var_hint)}
      >
        {field.env_var}
      </code>

      {source === 'db' && (
        <span
          className="rounded border border-primary-200 bg-primary-50 px-1.5 py-0.5 text-[10px] text-primary-700"
          // The shadowing case is the confusing one, so it gets its own copy
          // rather than a generic "overridden".
          title={
            field.env_set
              ? t(keys.settings.modules.source_db_shadows_env, { env_var: field.env_var })
              : t(keys.settings.modules.source_db_hint)
          }
        >
          {field.env_set
            ? t(keys.settings.modules.source_db_over_env)
            : t(keys.settings.modules.source_db)}
        </span>
      )}

      {source === 'env' && (
        <span
          className="rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-700"
          title={t(keys.settings.modules.source_env_hint, { env_var: field.env_var })}
        >
          {t(keys.settings.modules.source_env)}
        </span>
      )}

      {source === 'default' && (
        <span className="text-[10px] text-muted-foreground">
          {t(keys.settings.modules.source_default)}
        </span>
      )}
    </div>
  );
}
