import { keys, useT } from '@simple-module-py/i18n';

export default function Create() {
  const { t } = useT();
  return (
    <div className="p-6 max-w-xl">
      <h1 className="text-2xl font-semibold mb-4">{t(keys.catalog.create.title)}</h1>
      <form method="post" action="/catalog" className="space-y-3">
        <label className="block">
          <span className="block text-sm">{t(keys.catalog.form.name_label)}</span>
          <input name="name" required className="border rounded w-full p-2" />
        </label>
        <label className="block">
          <span className="block text-sm">
            {t(keys.catalog.form.description_label)}
          </span>
          <textarea name="description" className="border rounded w-full p-2" />
        </label>
        <button
          type="submit"
          className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
        >
          {t(keys.catalog.create.submit_button)}
        </button>
      </form>
    </div>
  );
}
