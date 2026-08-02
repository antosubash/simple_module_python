import { keys, useT } from '@simple-module-py/i18n';

type Catalog = {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
};

type Props = { catalog: Catalog };

export default function Edit({ catalog }: Props) {
  const { t } = useT();
  return (
    <div className="p-6 max-w-xl">
      <h1 className="text-2xl font-semibold mb-4">{t(keys.catalog.edit.title)}</h1>
      <form
        method="post"
        action={`/catalog/${catalog.id}`}
        className="space-y-3"
      >
        <input type="hidden" name="_method" value="put" />
        <label className="block">
          <span className="block text-sm">{t(keys.catalog.form.name_label)}</span>
          <input
            name="name"
            defaultValue={catalog.name}
            required
            className="border rounded w-full p-2"
          />
        </label>
        <label className="block">
          <span className="block text-sm">
            {t(keys.catalog.form.description_label)}
          </span>
          <textarea
            name="description"
            defaultValue={catalog.description ?? ""}
            className="border rounded w-full p-2"
          />
        </label>
        <button
          type="submit"
          className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
        >
          {t(keys.catalog.edit.submit_button)}
        </button>
      </form>
    </div>
  );
}
