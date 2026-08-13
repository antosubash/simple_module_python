import { router } from '@inertiajs/react';
import { useEffect, useMemo, useState } from 'react';
import { FieldInput, type FieldMeta } from './FieldInput';
import { FieldSource } from './FieldSource';
import { TestConnectionButton } from './TestConnectionButton';

export type ModuleView = {
  module_name: string;
  package: string;
  env_prefix: string;
  class_name: string;
  fields: FieldMeta[];
};

type Props = {
  module: ModuleView;
  /** True when this module registered health checks worth running on demand. */
  testable?: boolean;
};

function notEqual(a: unknown, b: unknown): boolean {
  if (a === b) return false;
  if (typeof a === 'object' || typeof b === 'object') {
    return JSON.stringify(a) !== JSON.stringify(b);
  }
  return true;
}

export function ModuleForm({ module: m, testable = false }: Props) {
  const initial = useMemo(() => {
    const o: Record<string, unknown> = {};
    for (const f of m.fields) o[f.name] = f.value;
    return o;
  }, [m.fields]);

  const [values, setValues] = useState<Record<string, unknown>>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  // Reset the edit buffer whenever the underlying module changes (package
  // switch, or server-reloaded props after a save/reset).
  useEffect(() => {
    setValues(initial);
    setErrors({});
  }, [initial]);

  const modifiedFields = useMemo(() => {
    const s = new Set<string>();
    for (const name of Object.keys(values)) {
      if (notEqual(values[name], initial[name])) s.add(name);
    }
    return s;
  }, [values, initial]);

  const defaultByName = useMemo(() => {
    const o: Record<string, unknown> = {};
    for (const f of m.fields) o[f.name] = f.default;
    return o;
  }, [m.fields]);

  const dirty = modifiedFields.size > 0;

  const grouped = useMemo(() => {
    const g: Record<string, FieldMeta[]> = {};
    for (const f of m.fields) {
      const key = f.group ?? 'General';
      if (!g[key]) g[key] = [];
      g[key].push(f);
    }
    return g;
  }, [m.fields]);

  async function onSave() {
    setBusy(true);
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
      router.reload({ only: ['modules'] });
    }
    setBusy(false);
  }

  async function onReset(name: string) {
    await fetch(`/api/settings/modules/${m.package}/${name}`, { method: 'DELETE' });
    router.reload({ only: ['modules'] });
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between border-b pb-3">
        <div>
          <h2 className="text-xl font-semibold">{m.module_name}</h2>
          <p className="text-xs font-mono text-muted-foreground">{m.package}</p>
        </div>
        <div className="flex items-start gap-2">
          {testable && <TestConnectionButton pkg={m.package} />}
          <button
            type="button"
            disabled={!dirty || busy}
            onClick={onSave}
            className="rounded bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
          >
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </header>

      {Object.entries(grouped).map(([group, fields]) => (
        <section key={group} className="space-y-3">
          <h3 className="text-sm font-semibold text-muted-foreground">{group}</h3>
          {fields.map((f) => {
            const isModified = notEqual(values[f.name], defaultByName[f.name]);
            return (
              <div key={f.name} className="grid grid-cols-[1fr_2fr] gap-4 items-start">
                <div>
                  <label htmlFor={`field-${m.package}-${f.name}`} className="font-mono text-xs">
                    {f.name}
                  </label>
                  {f.description && (
                    <p className="mt-1 text-xs text-muted-foreground">{f.description}</p>
                  )}
                  {f.requires_restart && isModified && (
                    <span className="mt-1 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[10px] uppercase text-amber-900">
                      Requires restart
                    </span>
                  )}
                  <FieldSource field={f} />
                </div>
                <div>
                  <FieldInput
                    id={`field-${m.package}-${f.name}`}
                    field={f}
                    value={values[f.name]}
                    onChange={(name, v) => setValues((prev) => ({ ...prev, [name]: v }))}
                  />
                  {isModified && (
                    <button
                      type="button"
                      onClick={() => onReset(f.name)}
                      className="mt-1 text-xs text-primary hover:underline"
                    >
                      Reset to default
                    </button>
                  )}
                  {errors[f.name] && <p className="mt-1 text-xs text-red-600">{errors[f.name]}</p>}
                </div>
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}
