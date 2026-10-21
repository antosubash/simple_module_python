import { Head, Link } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';

type Item = {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
};

export default function Browse({ items }: { items: Item[] }) {
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
      {items.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">No {{PACKAGE_NAME}} yet.</p>
      ) : (
        <ul className="divide-y">
          {items.map((item) => (
            <li key={item.id} className="flex justify-between py-2">
              <span>{item.name}</span>
              <Link href={`/{{MODULE_SLUG}}/${item.id}/edit`}>Edit</Link>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}
