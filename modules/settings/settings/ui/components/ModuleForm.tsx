import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { apiResult } from '@simple-module-py/ui/lib/api';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../pages/api.generated';
import { useSettingsText } from '../utils/field-text';
import { groupFields, notEqual } from '../utils/form-state';
import type { FieldMeta } from './FieldInput';
import { ModuleFieldRow } from './ModuleFieldRow';
import { SaveBar } from './SaveBar';
import { TestConnectionButton } from './TestConnectionButton';
import { splitValidationErrors } from './validation-errors';

export type ModuleView = {
  module_name: string;
  package: string;
  env_prefix: string;
  class_name: string;
  fields: FieldMeta[];
  /** The module's own management page; when set, the generic editor links there. */
  manage_url?: string | null;
};

type Props = {
  module: ModuleView;
  /** Names of the health checks this module registered, if any. */
  checks?: string[];
  onDirtyChange?: (dirty: boolean) => void;
};

export function ModuleForm({ module: m, checks = [], onDirtyChange }: Props) {
  const { t } = useT();
  const text = useSettingsText(m.package);
  const description = text.description();
  const initial = useMemo(() => {
    const o: Record<string, unknown> = {};
    for (const f of m.fields) o[f.name] = f.value;
    return o;
  }, [m.fields]);

  const [{ values, baseline }, setBuffer] = useState({ values: initial, baseline: initial });
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [saved, setSaved] = useState(false);
  const [savedOverrides, setSavedOverrides] = useState<Record<string, boolean>>({});
  const [formErrors, setFormErrors] = useState<string[]>([]);
  // Bumped after each successful save so secret editors remount masked.
  const [savedGeneration, setSavedGeneration] = useState(0);
  const fieldsRef = useRef<HTMLDivElement>(null);
  const focusFirstError = useRef(false);

  useEffect(() => {
    if (!focusFirstError.current) return;
    focusFirstError.current = false;
    fieldsRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
  }, [errors]);

  // Refresh saved values without discarding drafts in other fields (#637).
  useEffect(() => {
    setBuffer((prev) => ({
      values: Object.fromEntries(
        Object.entries(initial).map(([name, value]) => [
          name,
          notEqual(prev.values[name], prev.baseline[name]) ? prev.values[name] : value,
        ]),
      ),
      baseline: initial,
    }));
    setErrors({});
    setSaved(false);
    setSavedOverrides({});
  }, [initial]);

  const modifiedFields = useMemo(() => {
    const s = new Set<string>();
    for (const f of m.fields) {
      // An empty secret draft means "no new value yet", never "store blank".
      if (f.is_secret && values[f.name] === '') continue;
      if (notEqual(values[f.name], baseline[f.name])) s.add(f.name);
    }
    return s;
  }, [m.fields, values, baseline]);

  const dirty = modifiedFields.size > 0;
  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);

  const groups = useMemo(() => groupFields(m.fields), [m.fields]);

  function handleFailure(result: { status?: number; error?: unknown }) {
    if (result.status === 422) {
      const split = splitValidationErrors(
        (result.error as { detail?: unknown } | null)?.detail,
        m.fields.map((f) => f.name),
      );
      focusFirstError.current = true;
      setErrors(split.fields);
      setFormErrors(split.form);
    } else {
      setFormErrors([t(keys.settings.modules_form.save_failed)]);
    }
  }

  async function onSave() {
    if (submitting.current || !dirty) return;
    submitting.current = true;
    setBusy(true);
    setSaved(false);
    setErrors({});
    setFormErrors([]);
    const changed: Record<string, unknown> = {};
    for (const name of modifiedFields) changed[name] = values[name];
    const result = await apiResult(
      api.PUT('/api/settings/modules/{package}', {
        params: { path: { package: m.package } },
        body: changed,
      }),
    );
    if (!result.ok) {
      handleFailure(result);
    } else {
      // Keeping the form mounted lets the confirmation remain visible instead
      // of being discarded by an immediate Inertia reload.
      // A saved secret goes back to its mask: the typed value leaves the form.
      const masked = Object.fromEntries(
        m.fields.filter((f) => f.is_secret && f.name in changed).map((f) => [f.name, f.value]),
      );
      setBuffer((prev) => ({
        values: { ...prev.values, ...masked },
        baseline: { ...values, ...masked },
      }));
      setSavedGeneration((n) => n + 1);
      setSavedOverrides((prev) => ({
        ...prev,
        ...Object.fromEntries(
          m.fields
            .filter((f) => f.name in changed)
            .map((f) => [f.name, notEqual(changed[f.name], f.default)]),
        ),
      }));
      setSaved(true);
    }
    setBusy(false);
    submitting.current = false;
  }

  async function onReset(name: string): Promise<boolean> {
    if (submitting.current) return false;
    submitting.current = true;
    setBusy(true);
    setSaved(false);
    setErrors({});
    setFormErrors([]);
    const result = await apiResult(
      api.DELETE('/api/settings/modules/{package}/{field}', {
        params: { path: { package: m.package, field: name } },
      }),
    );
    if (!result.ok) {
      handleFailure(result);
      setBusy(false);
      submitting.current = false;
      return false;
    }
    setSavedOverrides((prev) => ({ ...prev, [name]: false }));
    setBuffer((prev) => ({
      ...prev,
      values: { ...prev.values, [name]: prev.baseline[name] },
    }));
    // Take the field's live value from the reload itself: when the page never
    // reloaded after a save, the fresh props equal the old ones and the
    // [initial] effect does not fire, leaving the reverted value on screen.
    router.reload({
      only: ['modules'],
      onSuccess: (page) => {
        const modules = (page.props as { modules?: ModuleView[] }).modules ?? [];
        const fresh = modules
          .find((other) => other.package === m.package)
          ?.fields.find((f) => f.name === name);
        if (!fresh) return;
        setBuffer((prev) => ({
          values: { ...prev.values, [name]: fresh.value },
          baseline: { ...prev.baseline, [name]: fresh.value },
        }));
      },
    });
    setBusy(false);
    submitting.current = false;
    return true;
  }

  function onDiscard() {
    setBuffer((prev) => ({ ...prev, values: prev.baseline }));
    setErrors({});
    setFormErrors([]);
    setSaved(false);
    // Secret editors remount masked rather than keep a half-typed value.
    setSavedGeneration((n) => n + 1);
  }

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-5">
      <header>
        <h2 className="font-display text-2xl font-bold tracking-tight">{text.title()}</h2>
        {description && (
          <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">{description}</p>
        )}
      </header>

      {formErrors.length > 0 && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
        >
          <p className="font-medium">{t(keys.settings.modules_form.validation_failed)}</p>
          <ul className="mt-1 list-disc pl-5">
            {formErrors.map((msg) => (
              <li key={msg}>{msg}</li>
            ))}
          </ul>
        </div>
      )}

      {/* No inner scroller: the cards grow and the page scrolls, which is one
          scrollbar for the screen instead of nested ones. */}
      <div ref={fieldsRef} className="flex flex-col gap-5">
        {groups.map(([group, fields]) => (
          <Card
            key={group}
            role="group"
            aria-label={group ? text.group(group) : undefined}
            className="@container gap-0 overflow-hidden border-border p-0"
          >
            {group && (
              <h3 className="border-b border-border px-4 py-3 text-sm font-semibold text-muted-foreground @lg:px-6">
                {text.group(group)}
              </h3>
            )}
            <div className="divide-y divide-border/70">
              {fields.map((f) => (
                <ModuleFieldRow
                  key={f.is_secret ? `${f.name}:${savedGeneration}` : f.name}
                  field={{
                    ...f,
                    value: baseline[f.name],
                    db_override: savedOverrides[f.name] ?? f.db_override,
                  }}
                  package={m.package}
                  value={values[f.name]}
                  modified={modifiedFields.has(f.name)}
                  // Cancel must not restore a stale secret mask during a save.
                  disabled={busy && f.is_secret}
                  error={errors[f.name]}
                  onReset={() => onReset(f.name)}
                  onChange={(name, v) => {
                    setSaved(false);
                    setErrors((prev) => (prev[name] ? { ...prev, [name]: undefined } : prev));
                    setBuffer((prev) => ({
                      ...prev,
                      values: { ...prev.values, [name]: v },
                    }));
                  }}
                />
              ))}
            </div>
          </Card>
        ))}
      </div>

      {checks.length > 0 && <TestConnectionButton pkg={m.package} checks={checks} />}

      <SaveBar
        unsaved={modifiedFields.size}
        busy={busy}
        saved={saved}
        onSave={onSave}
        onDiscard={onDiscard}
      />
    </div>
  );
}
