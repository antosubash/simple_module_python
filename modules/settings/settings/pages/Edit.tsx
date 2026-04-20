import { useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import type React from 'react';
import ValueInput, { type ValueType } from './components/ValueInput';
import { ROUTES } from './routes';

type Scope = 'system' | 'tenant' | 'user';

type Setting = {
  id: number;
  scope: Scope;
  scope_id: string;
  key: string;
  value: string;
  value_type: ValueType;
  description: string | null;
};

type Props = { setting: Setting };

function Edit({ setting }: Props) {
  const { t } = useT();
  const { data, setData, put, processing, errors } = useForm({
    value: setting.value,
    value_type: setting.value_type,
    description: setting.description ?? '',
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    put(ROUTES.byId(setting.id));
  }

  return (
    <div className="p-6 max-w-xl">
      <h1 className="text-2xl font-semibold mb-4">{t(keys.settings.edit.title)}</h1>
      <form onSubmit={handleSubmit} className="space-y-3">
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.scope_label)}</span>
          <input
            value={t(keys.settings.scopes[setting.scope])}
            disabled
            className="border rounded w-full p-2 bg-muted"
          />
        </label>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.scope_id_label)}</span>
          <input
            value={setting.scope_id}
            disabled
            className="border rounded w-full p-2 font-mono bg-muted"
          />
        </label>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.key_label)}</span>
          <input
            defaultValue={setting.key}
            disabled
            className="border rounded w-full p-2 font-mono bg-muted"
          />
        </label>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.value_type_label)}</span>
          <input
            value={t(keys.settings.value_types[setting.value_type])}
            disabled
            className="border rounded w-full p-2 bg-muted"
          />
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
            className="border rounded w-full p-2"
          />
        </label>
        <button
          type="submit"
          disabled={processing}
          className="rounded bg-primary px-3 py-1.5 text-primary-foreground disabled:opacity-50"
        >
          {t(keys.settings.edit.submit_button)}
        </button>
      </form>
    </div>
  );
}

Edit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Edit;
