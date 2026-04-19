import { keys, useT } from '@simple-module/i18n';
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

export default function Edit({ setting }: Props) {
  const { t } = useT();
  return (
    <div className="p-6 max-w-xl">
      <h1 className="text-2xl font-semibold mb-4">{t(keys.settings.edit.title)}</h1>
      <form method="post" action={ROUTES.byId(setting.id)} className="space-y-3">
        <input type="hidden" name="_method" value="put" />
        <input type="hidden" name="value_type" value={setting.value_type} />
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
            name="key"
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
          <ValueInput valueType={setting.value_type} defaultValue={setting.value} required />
        </div>
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.description_label)}</span>
          <textarea
            name="description"
            defaultValue={setting.description ?? ''}
            className="border rounded w-full p-2"
          />
        </label>
        <button type="submit" className="rounded bg-primary px-3 py-1.5 text-primary-foreground">
          {t(keys.settings.edit.submit_button)}
        </button>
      </form>
    </div>
  );
}
