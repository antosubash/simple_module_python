import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { useEffect, useMemo, useState } from 'react';
import type { FieldMeta } from './FieldInput';
import { ModuleFieldRow } from './ModuleFieldRow';
import { TestConnectionButton } from './TestConnectionButton';

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
};

function notEqual(a: unknown, b: unknown): boolean {
  if (a === b) return false;
  if (typeof a === 'object' || typeof b === 'object') {
    return JSON.stringify(a) !== JSON.stringify(b);
  }
  return true;
}

export function ModuleForm({ module: m, checks = [] }: Props) {
  const { t } = useT();
  const initial = useMemo(() => {
    const o: Record<string, unknown> = {};
    for (const f of m.fields) o[f.name] = f.value;
    return o;
  }, [m.fields]);

  const [values, setValues] = useState<Record<string, unknown>>(initial);
  const [baseline, setBaseline] = useState<Record<string, unknown>>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  // Reset the edit buffer whenever the underlying module changes (package
  // switch, or server-reloaded props after a save/reset).
  useEffect(() => {
    setValues(initial);
    setBaseline(initial);
    setErrors({});
    setSaved(false);
  }, [initial]);

  const modifiedFields = useMemo(() => {
    const s = new Set<string>();
    for (const name of Object.keys(values)) {
      if (notEqual(values[name], baseline[name])) s.add(name);
    }
    return s;
  }, [values, baseline]);

  const dirty = modifiedFields.size > 0;

  // Grouped only where the module said so. A single "General" heading over
  // every field of a module that declared no groups is a heading that carries
  // no information and costs a row of vertical space per module.
  const groups = useMemo(() => {
    const g = new Map<string, FieldMeta[]>();
    for (const f of m.fields) {
      const key = f.group ?? '';
      const bucket = g.get(key);
      if (bucket) bucket.push(f);
      else g.set(key, [f]);
    }
    return [...g.entries()];
  }, [m.fields]);

  async function onSave() {
    setBusy(true);
    setSaved(false);
    setErrors({});
    const changed: Record<string, unknown> = {};
    for (const name of modifiedFields) changed[name] = values[name];
    const resp = await fetch(`/api/settings/modules/${m.package}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changed),
    });
    if (resp.status === 422) {
      const body = await resp.json();
      const fieldErrs: Record<string, string> = {};
      for (const d of body.detail ?? []) {
        if (d.loc?.length) fieldErrs[d.loc[d.loc.length - 1]] = d.msg;
      }
      setErrors(fieldErrs);
    } else if (resp.ok) {
      // Keeping the form mounted lets the confirmation remain visible instead
      // of being discarded by an immediate Inertia reload.
      setBaseline({ ...values });
      setSaved(true);
    }
    setBusy(false);
  }

  async function onReset(name: string) {
    setSaved(false);
    await fetch(`/api/settings/modules/${m.package}/${name}`, { method: 'DELETE' });
    router.reload({ only: ['modules'] });
  }

  return (
    <div className="flex flex-1 flex-col gap-4">
      {/* Outside the card: the heading names the pane, and the deck keeps the
          card for the fields alone. */}
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">
            <code className="font-mono text-[22px]">{m.package}</code>{' '}
            {t(keys.settings.modules.heading_suffix)}
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {t(keys.settings.modules.description)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2.5">
          {saved && (
            <p role="status" className="text-sm font-medium text-primary-700">
              {t(keys.settings.modules_form.saved_toast)}
            </p>
          )}
          {dirty && (
            <p className="text-[13px] text-muted-foreground">
              {t(keys.settings.modules.unsaved_count, { count: modifiedFields.size })}
            </p>
          )}
          <Button type="button" disabled={!dirty || busy} onClick={onSave} className="min-h-11">
            {busy ? t(keys.settings.modules_form.saving) : t(keys.settings.modules_form.save)}
          </Button>
        </div>
      </header>

      <Card className="flex flex-1 flex-col gap-4 border-border p-6">
        {/* No inner scroller: the card grows and the page scrolls, which is
            one scrollbar for the screen instead of three nested ones. */}
        <div className="flex flex-col gap-4">
          {groups.map(([group, fields]) => (
            <section key={group} className="flex flex-col gap-4">
              {group && <h2 className="text-sm font-semibold text-muted-foreground">{group}</h2>}
              {fields.map((f) => (
                <ModuleFieldRow
                  key={f.name}
                  field={f}
                  package={m.package}
                  value={values[f.name]}
                  modified={modifiedFields.has(f.name)}
                  error={errors[f.name]}
                  onReset={() => onReset(f.name)}
                  onChange={(name, v) => {
                    setSaved(false);
                    setValues((prev) => ({ ...prev, [name]: v }));
                  }}
                />
              ))}
            </section>
          ))}
        </div>

        {checks.length > 0 && (
          <div className="mt-auto border-t pt-4">
            <TestConnectionButton pkg={m.package} checks={checks} />
          </div>
        )}
      </Card>
    </div>
  );
}
