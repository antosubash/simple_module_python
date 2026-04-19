import { keys, useT } from '@simple-module/i18n';

type Setting = {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
};

type Props = { setting: Setting };

export default function Edit({ setting }: Props) {
  const { t } = useT();
  return (
    <div className="p-6 max-w-xl">
      <h1 className="text-2xl font-semibold mb-4">{t(keys.settings.edit.title)}</h1>
      <form method="post" action={`/settings/${setting.id}`} className="space-y-3">
        <input type="hidden" name="_method" value="put" />
        <label className="block">
          <span className="block text-sm">{t(keys.settings.form.name_label)}</span>
          <input
            name="name"
            defaultValue={setting.name}
            required
            className="border rounded w-full p-2"
          />
        </label>
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
