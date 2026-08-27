import { Head, Link, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { NavIcon } from '@simple-module-py/ui/components/NavIcon';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import type { MenuItem, SharedProps } from '@simple-module-py/ui/types';
import type React from 'react';

/**
 * Admin section landing page.
 *
 * Built from the `adminSidebar` shared prop rather than a list of its own:
 * that prop is already filtered by the viewer's roles and permissions, so a
 * card here can never advertise a screen its owner cannot open — and adding a
 * module contributes a card with no change to this file.
 */

/** Group entries in registration order, so cards match sidebar order. */
function groupItems(items: MenuItem[]): [string, MenuItem[]][] {
  const groups = new Map<string, MenuItem[]>();
  for (const item of items) {
    const key = item.group || '';
    const existing = groups.get(key);
    if (existing) existing.push(item);
    else groups.set(key, [item]);
  }
  return [...groups.entries()];
}

function ToolCard({ item }: { item: MenuItem }) {
  return (
    <Link
      href={item.url}
      className="group flex items-start gap-3 rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-accent/40"
    >
      <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
        <NavIcon name={item.icon} />
      </span>
      <span className="min-w-0">
        <span className="block truncate font-medium text-foreground group-hover:text-primary">
          {item.label}
        </span>
        {/* The url is the card's only disambiguator when two tools share a
            label, so clipping it silently makes them indistinguishable. */}
        <span title={item.url} className="block truncate text-sm text-muted-foreground">
          {item.url}
        </span>
      </span>
    </Link>
  );
}

function AdminPage() {
  const { t } = useT();
  const { menus } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const items = menus?.adminSidebar ?? [];
  const grouped = groupItems(items);

  return (
    <>
      <Head title={t(keys.host.admin.title)} />
      <PageShell title={t(keys.host.admin.title)} description={t(keys.host.admin.description)}>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t(keys.host.admin.empty)}</p>
        ) : (
          <div className="space-y-8">
            {grouped.map(([group, groupItems_]) => (
              <section key={group || 'ungrouped'}>
                {group && (
                  <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {group}
                  </h2>
                )}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {groupItems_.map((item) => (
                    <ToolCard key={item.url} item={item} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </PageShell>
    </>
  );
}

AdminPage.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;

export default AdminPage;
