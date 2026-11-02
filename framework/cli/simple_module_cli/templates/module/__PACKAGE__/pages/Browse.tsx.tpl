import { Head, Link, router } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { apiResult } from '@simple-module-py/ui/lib/api';
import { useState } from 'react';
import { api } from './api';
import type { components } from './api.generated';

/** The API's DTO, generated from `{{SINGULAR_CLASS}}Out` — the view sends the same shape. */
type Item = components['schemas']['{{SINGULAR_CLASS}}Out'];

export default function Browse({ items }: { items: Item[] }) {
  const [error, setError] = useState<string | null>(null);

  async function remove(item: Item) {
    setError(null);
    const result = await apiResult(
      api.DELETE('/api/{{MODULE_SLUG}}/{item_id}', { params: { path: { item_id: item.id } } }),
    );
    if (!result.ok) {
      setError(result.detail ?? 'Could not delete');
      return;
    }
    router.reload({ only: ['items'] });
  }

  return (
    <PageShell title="{{MODULE_NAME}}" description="Manage your {{PACKAGE_NAME}}">
      <Head title="{{MODULE_NAME}}" />
      <div className="mb-4 flex justify-end">
        <Link
          href="/{{MODULE_SLUG}}/create"
          className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
        >
          New {{SINGULAR_CLASS}}
        </Link>
      </div>
      {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
      {items.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">No {{PACKAGE_NAME}} yet.</p>
      ) : (
        <ul className="divide-y">
          {items.map((item) => (
            <li key={item.id} className="flex justify-between gap-4 py-2">
              <span>{item.name}</span>
              <span className="flex gap-3">
                <Link href={`/{{MODULE_SLUG}}/${item.id}/edit`}>Edit</Link>
                <button type="button" onClick={() => remove(item)}>
                  Delete
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}
