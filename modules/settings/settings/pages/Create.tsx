import { useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import type React from 'react';
import ValueInput, { VALUE_TYPES, type ValueType } from './components/ValueInput';
import { ROUTES } from './routes';

const SCOPES = ['system', 'tenant', 'user'] as const;
type Scope = (typeof SCOPES)[number];

function Create() {
  const { t } = useT();
  const { data, setData, post, processing, errors } = useForm({
    scope: 'system' as Scope,
    scope_id: '',
    key: '',
    value_type: 'string' as ValueType,
    value: '',
    description: '',
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    post(ROUTES.browse);
  }

  return (
    <div className="p-6 max-w-xl">
      <h1 className="text-2xl font-semibold mb-4">{t(keys.settings.create.title)}</h1>
      <form onSubmit={handleSubmit} className="space-y-3">
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.scope_label)}</span>
          <select
            value={data.scope}
            onChange={(e) => setData('scope', e.target.value as Scope)}
            className="border rounded w-full p-2"
          >
            {SCOPES.map((s) => (
              <option key={s} value={s}>
                {t(keys.settings.scopes[s])}
              </option>
            ))}
          </select>
          {errors.scope && <p className="text-sm text-destructive">{errors.scope}</p>}
        </label>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.scope_id_label)}</span>
          <input
            value={data.scope_id}
            onChange={(e) => setData('scope_id', e.target.value)}
            placeholder={t(keys.settings.form.scope_id_placeholder)}
            className="border rounded w-full p-2 font-mono"
          />
          {errors.scope_id && <p className="text-sm text-destructive">{errors.scope_id}</p>}
        </label>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.key_label)}</span>
          <input
            value={data.key}
            onChange={(e) => setData('key', e.target.value)}
            required
            placeholder={t(keys.settings.form.key_placeholder)}
            className="border rounded w-full p-2 font-mono"
          />
          {errors.key && <p className="text-sm text-destructive">{errors.key}</p>}
        </label>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.value_type_label)}</span>
          <select
            value={data.value_type}
            onChange={(e) => setData('value_type', e.target.value as ValueType)}
            className="border rounded w-full p-2"
          >
            {VALUE_TYPES.map((vt) => (
              <option key={vt} value={vt}>
                {t(keys.settings.value_types[vt])}
              </option>
            ))}
          </select>
        </label>
        <div className="block">
          <span className="block text-sm">{t(keys.settings.form.value_label)}</span>
          <ValueInput
            valueType={data.value_type}
            value={data.value}
            onValueChange={(v) => setData('value', v)}
            required
          />
          {errors.value && <p className="text-sm text-destructive">{errors.value}</p>}
        </div>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.description_label)}</span>
          <textarea
            value={data.description}
            onChange={(e) => setData('description', e.target.value)}
            placeholder={t(keys.settings.form.description_placeholder)}
            className="border rounded w-full p-2"
          />
        </label>
        <button
          type="submit"
          disabled={processing}
          className="rounded bg-primary px-3 py-1.5 text-primary-foreground disabled:opacity-50"
        >
          {t(keys.settings.create.submit_button)}
        </button>
      </form>
    </div>
  );
}

Create.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Create;
