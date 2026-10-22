import { Head, Link, router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { useApiErrorToast } from '@simple-module-py/ui/hooks/use-api-error-toast';
import { apiResult } from '@simple-module-py/ui/lib/api';
import { api } from './api';
import type { components } from './api.generated';

/** The API's DTO, generated from `{{SINGULAR_CLASS}}Out` — the view sends the same shape. */
type Item = components['schemas']['{{SINGULAR_CLASS}}Out'];

export default function Browse({ items }: { items: Item[] }) {
  const { t } = useT();
  const showError = useApiErrorToast(keys.{{PACKAGE_NAME}}.browse.delete_failed);
  const editLabel = t(keys.{{PACKAGE_NAME}}.browse.edit_link);

  async function remove(item: Item) {
    const result = await apiResult(
      api.DELETE('/api/{{MODULE_SLUG}}/{item_id}', { params: { path: { item_id: item.id } } }),
    );
    showError(result);
    if (result.ok) router.reload({ only: ['items'] });
  }

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
            <li key={item.id} className="flex justify-between gap-4 py-2">
              <span>{item.name}</span>
              <span className="flex gap-3">
                <Link href={`/{{MODULE_SLUG}}/${item.id}/edit`}>{editLabel}</Link>
                <button type="button" onClick={() => remove(item)}>
                  {t(keys.{{PACKAGE_NAME}}.browse.delete_button)}
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}
