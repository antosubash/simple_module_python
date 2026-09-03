import { Head, router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { Plus, Search, Settings as SettingsIcon, Trash2 } from 'lucide-react';
import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { type ScopeCounts, type ScopeFilter, ScopeTabs } from './components/ScopeTabs';
import { StoreTable } from './components/StoreTable';
import { ROUTES } from './routes';
import type { Pagination, Setting } from './types';

interface Props {
  settings: Setting[];
  pagination: Pagination;
  counts: ScopeCounts;
  filters: { scope: ScopeFilter; q: string };
}

function Browse({ settings, pagination, counts, filters }: Props) {
  const { t } = useT();
  const [search, setSearch] = useState(filters.q);
  const [pendingDelete, setPendingDelete] = useState<Setting | null>(null);

  const navigate = useCallback(
    (next: Partial<{ scope: ScopeFilter; q: string; page: number }>) => {
      const scope = next.scope ?? filters.scope;
      const q = next.q ?? search;
      const page = next.page ?? 1;
      const params: Record<string, string> = {};
      if (scope !== 'all') params.scope = scope;
      if (q) params.q = q;
      if (page > 1) params.page = String(page);
      router.get(ROUTES.browse, params, { preserveState: true, preserveScroll: true });
    },
    [filters.scope, search],
  );

  // Debounced so a five-letter key is one request rather than five, and
  // `preserveState` above keeps the caret where it was between them.
  useEffect(() => {
    if (search === filters.q) return;
    const timeout = setTimeout(() => navigate({ q: search }), 300);
    return () => clearTimeout(timeout);
  }, [search, filters.q, navigate]);

  const { page, per_page, total } = pagination;
  const from = total === 0 ? 0 : (page - 1) * per_page + 1;
  const to = Math.min(page * per_page, total);
  const lastPage = Math.max(1, Math.ceil(total / per_page));
  const isFiltered = !!filters.q || filters.scope !== 'all';

  function confirmDelete() {
    if (!pendingDelete) return;
    router.delete(ROUTES.byId(pendingDelete.id));
    setPendingDelete(null);
  }

  return (
    <>
      <Head title={t(keys.settings.browse.title)} />
      <PageShell
        title={t(keys.settings.browse.title)}
        description={t(keys.settings.browse.description)}
        actions={
          <>
            <Button asChild variant="outline">
              <a href={ROUTES.modules}>{t(keys.settings.modules.browse_link)}</a>
            </Button>
            <Button asChild className="gap-1.5">
              <a href={ROUTES.create}>
                <Plus className="h-4 w-4" aria-hidden="true" />
                {t(keys.settings.browse.new_button)}
              </a>
            </Button>
          </>
        }
      >
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <ScopeTabs
            value={filters.scope}
            counts={counts}
            onChange={(scope) => navigate({ scope, page: 1 })}
          />
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t(keys.settings.browse.search_placeholder)}
              className="pl-9 max-lg:min-h-11"
            />
          </div>
        </div>

        {/* A min-height rather than a fixed one: the deck's card fills the
            viewport with the footer pinned to the bottom, and `min-h` gets
            that look without clipping a full page of rows on a short window. */}
        <Card className="flex flex-col overflow-hidden border-border p-0 lg:min-h-[calc(100vh-var(--app-chrome-h)-15rem)]">
          {settings.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 py-16 text-muted-foreground">
              <SettingsIcon className="size-8" aria-hidden="true" />
              <h2 className="font-display text-base font-semibold text-foreground">
                {isFiltered
                  ? t(keys.settings.browse.no_match_title)
                  : t(keys.settings.browse.empty_title)}
              </h2>
              <p className="text-sm">
                {isFiltered
                  ? t(keys.settings.browse.no_match_description)
                  : t(keys.settings.browse.empty_description)}
              </p>
            </div>
          ) : (
            <StoreTable settings={settings} onDelete={setPendingDelete} />
          )}

          <div className="mt-auto flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground">
            <span>{t(keys.settings.browse.showing, { from, to, total })}</span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                className="max-lg:min-h-11"
                disabled={page <= 1}
                onClick={() => navigate({ page: page - 1 })}
              >
                {t(keys.settings.browse.previous)}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="max-lg:min-h-11"
                disabled={page >= lastPage}
                onClick={() => navigate({ page: page + 1 })}
              >
                {t(keys.settings.browse.next)}
              </Button>
            </div>
          </div>
        </Card>
      </PageShell>

      <ConfirmActionDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        icon={Trash2}
        title={t(keys.settings.browse.delete_title)}
        description={t(keys.settings.browse.delete_description, { key: pendingDelete?.key ?? '' })}
        confirmLabel={t(keys.settings.browse.delete_confirm_button)}
        cancelLabel={t(keys.settings.form.cancel_button)}
        onConfirm={confirmDelete}
      />
    </>
  );
}

Browse.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Browse;
