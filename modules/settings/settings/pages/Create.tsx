import { keys, useT } from '@simple-module/i18n';
import { useState } from 'react';
import ValueInput, { VALUE_TYPES, type ValueType } from './components/ValueInput';
import { ROUTES } from './routes';

const SCOPES = ['system', 'tenant', 'user'] as const;

export default function Create() {
  const { t } = useT();
  const [valueType, setValueType] = useState<ValueType>('string');
  return (
    <div className="p-6 max-w-xl">
      <h1 className="text-2xl font-semibold mb-4">{t(keys.settings.create.title)}</h1>
      <form method="post" action={ROUTES.browse} className="space-y-3">
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.scope_label)}</span>
          <select name="scope" defaultValue="system" className="border rounded w-full p-2">
            {SCOPES.map((s) => (
              <option key={s} value={s}>
                {t(keys.settings.scopes[s])}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.scope_id_label)}</span>
          <input
            name="scope_id"
            placeholder={t(keys.settings.form.scope_id_placeholder)}
            className="border rounded w-full p-2 font-mono"
          />
        </label>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.key_label)}</span>
          <input
            name="key"
            required
            placeholder={t(keys.settings.form.key_placeholder)}
            className="border rounded w-full p-2 font-mono"
          />
        </label>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.value_type_label)}</span>
          <select
            name="value_type"
            value={valueType}
            onChange={(e) => setValueType(e.target.value as ValueType)}
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
          <ValueInput valueType={valueType} required />
        </div>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.description_label)}</span>
          <textarea
            name="description"
            placeholder={t(keys.settings.form.description_placeholder)}
            className="border rounded w-full p-2"
          />
        </label>
        <button type="submit" className="rounded bg-primary px-3 py-1.5 text-primary-foreground">
          {t(keys.settings.create.submit_button)}
        </button>
      </form>
    </div>
  );
}
