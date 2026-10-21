import { Head, Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';

type Item = {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
};

export default function Browse({ items }: { items: Item[] }) {
  const { t } = useT();
  const editLabel = t(keys.{{PACKAGE_NAME}}.browse.edit_link);
  return (
    <PageShell
      title={t(keys.{{PACKAGE_NAME}}.browse.title)}
      description={t(keys.{{PACKAGE_NAME}}.browse.description)}
    >
      <Head title={t(keys.{{PACKAGE_NAME}}.browse.title)} />
      <div className="mb-4 flex justify-end">
        <Link
          href="/{{MODULE_SLUG}}/create"
          className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
        >
          {t(keys.{{PACKAGE_NAME}}.browse.new_button)}
        </Link>
      </div>
      {items.length === 0 ? (
        <div className="py-12 text-center">
          <h2 className="text-lg font-medium">{t(keys.{{PACKAGE_NAME}}.browse.empty_title)}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {t(keys.{{PACKAGE_NAME}}.browse.empty_description)}
          </p>
        </div>
      ) : (
        <ul className="divide-y">
          {items.map((item) => (
            <li key={item.id} className="flex justify-between py-2">
              <span>{item.name}</span>
              <Link href={`/{{MODULE_SLUG}}/${item.id}/edit`}>{editLabel}</Link>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}
