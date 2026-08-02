import { keys, useT } from '@simple-module-py/i18n';

type Catalog = {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
};

type Props = { catalog: Catalog[] };

export default function Browse({ catalog }: Props) {
  const { t } = useT();
  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">{t(keys.catalog.browse.title)}</h1>
        <a
          href="/catalog/create"
          className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
        >
          {t(keys.catalog.browse.new_button)}
        </a>
      </div>
      {catalog.length === 0 ? (
        <div className="py-12 text-center">
          <h2 className="text-lg font-medium">{t(keys.catalog.browse.empty_title)}</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {t(keys.catalog.browse.empty_description)}
          </p>
        </div>
      ) : (
        <ul className="divide-y">
          {catalog.map((catalog) => (
            <li key={catalog.id} className="py-2 flex justify-between">
              <span>{catalog.name}</span>
              <a href={`/catalog/${catalog.id}/edit`}>
                {t(keys.catalog.browse.edit_link)}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
