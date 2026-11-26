import { keys, useT } from '@simple-module-py/i18n';
import { useEffect, useId, useRef } from 'react';
import { useSettingsText } from '../utils/field-text';
import { FieldInput, type FieldMeta } from './FieldInput';
import { FieldSource } from './FieldSource';

interface Props {
  field: FieldMeta;
  package: string;
  value: unknown;
  /** Dirty relative to the saved baseline, not to the default. */
  modified: boolean;
  disabled?: boolean;
  error?: string;
  onChange: (name: string, value: unknown) => void;
  /** May resolve `false` when the revert failed or was ignored. */
  onReset: () => unknown;
}

/** A plain on/off switch sits beside its label, like every settings list. */
function isSwitch(field: FieldMeta): boolean {
  return (
    (field.input_type ?? field.type) === 'bool' &&
    !field.nullable &&
    !field.is_secret &&
    !field.control
  );
}

/**
 * One settings row: translated label and help, the control, and the source
 * line under it. Label and control sit side by side once the editor card has
 * room (a container query on the card, since two sidebars can leave a narrow
 * card on a wide screen), and stack otherwise. The raw identifier stays
 * reachable as the label's tooltip for anyone matching it to code or the CLI.
 */
export function ModuleFieldRow({
  field,
  package: pkg,
  value,
  modified,
  disabled,
  error,
  onChange,
  onReset,
}: Props) {
  const { t } = useT();
  const text = useSettingsText(pkg);
  const label = text.label(field);
  const help = text.help(field);
  const id = `field-${pkg}-${field.name}`;
  const descriptionId = useId();
  const errorId = useId();
  const describedBy =
    [help && descriptionId, error && errorId].filter(Boolean).join(' ') || undefined;
  // Revert is shown only while `db_override` is set, so a successful revert
  // unmounts the focused button and drops focus to the page. Move it to the
  // field once that has rendered. A failed revert keeps the button (a 422
  // moves focus to the first invalid field instead, in ModuleForm).
  const refocusAfterRevert = useRef(false);
  const revertInFlight = useRef(false);
  useEffect(() => {
    if (field.db_override || !refocusAfterRevert.current) return;
    refocusAfterRevert.current = false;
    if (document.activeElement === document.body) document.getElementById(id)?.focus();
  }, [field.db_override, id]);

  const switchRow = isSwitch(field);
  const control = (
    // An env-set field always wins over a stored value (env → DB → default),
    // so the server refuses edits to it; a disabled fieldset stops the form
    // from collecting an edit that would 422 the whole save.
    <fieldset disabled={!!field.env_set || disabled} className="min-w-0 border-0 p-0">
      <FieldInput
        id={id}
        aria-describedby={describedBy}
        aria-invalid={!!error}
        field={field}
        value={value}
        onChange={onChange}
        choiceLabel={(choice) => text.choice(field, choice)}
      />
    </fieldset>
  );
  const source = (
    <FieldSource
      field={field}
      label={label}
      value={value}
      modified={modified}
      onReset={async () => {
        // A second click while this row's revert is in flight is ignored
        // by the form; it must not cancel the first one's refocus.
        if (revertInFlight.current) return;
        revertInFlight.current = true;
        refocusAfterRevert.current = true;
        const result = await onReset();
        revertInFlight.current = false;
        if (result === false) refocusAfterRevert.current = false;
      }}
    />
  );
  // A switch at its default says everything with its position; a badge
  // reading "Default" under every toggle would be noise.
  const showSource = !switchRow || modified || field.db_override || field.env_set;

  return (
    <div
      data-testid={`row-${id}`}
      data-modified={modified || undefined}
      className={`grid grid-cols-1 gap-x-8 gap-y-3 px-4 py-4 transition-colors @lg:px-6 ${
        switchRow ? '' : '@xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]'
      } ${modified ? 'bg-amber-50/70 dark:bg-amber-400/5' : ''}`}
    >
      <div className="flex min-w-0 items-start gap-4">
        <div className="min-w-0 flex-1">
          <label
            htmlFor={id}
            title={field.name}
            className="block [overflow-wrap:anywhere] text-sm font-semibold text-foreground"
          >
            {label}
          </label>
          {help && (
            <p
              id={descriptionId}
              className="mt-1 [overflow-wrap:anywhere] text-[13px] leading-snug text-muted-foreground"
            >
              {help}
            </p>
          )}
          {field.requires_restart && modified && (
            <span className="mt-1.5 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-amber-800 dark:bg-amber-400/15 dark:text-amber-300">
              {t(keys.settings.modules_form.requires_restart)}
            </span>
          )}
          {switchRow && showSource && <div className="mt-2">{source}</div>}
        </div>
        {switchRow && <div className="shrink-0 pt-0.5">{control}</div>}
      </div>

      {!switchRow && (
        <div className="flex min-w-0 flex-col gap-2">
          {control}
          {source}
        </div>
      )}

      {error && (
        <p
          id={errorId}
          role="alert"
          data-testid={`field-error-${field.name}`}
          className={`min-w-0 [overflow-wrap:anywhere] text-xs text-destructive ${
            switchRow ? '' : '@xl:col-start-2'
          }`}
        >
          {error}
        </p>
      )}
    </div>
  );
}
