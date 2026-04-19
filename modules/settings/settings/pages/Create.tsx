import { keys, useT } from '@simple-module/i18n';
import { ROUTES } from './routes';

export default function Create() {
  const { t } = useT();
  return (
    <div className="p-6 max-w-xl">
      <h1 className="text-2xl font-semibold mb-4">{t(keys.settings.create.title)}</h1>
      <form method="post" action={ROUTES.browse} className="space-y-3">
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
          <span className="block text-sm">{t(keys.settings.form.value_label)}</span>
          <input
            name="value"
            required
            placeholder={t(keys.settings.form.value_placeholder)}
            className="border rounded w-full p-2"
          />
        </label>
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
