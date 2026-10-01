import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { EmptyState } from '@simple-module-py/ui/components/EmptyState';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { Building2, Search } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { type AdminTenant, AdminTenantsTable } from '../components/AdminTenantsTable';

interface Props {
  tenants: AdminTenant[];
  q: string;
  page: number;
  has_more: boolean;
}

const VIEW_URL = '/admin/tenants/';

function AdminBrowse() {
  const { tenants, q, page, has_more } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const [search, setSearch] = useState(q);

  const navigate = useCallback(
    (next: Partial<{ q: string; page: number }>) => {
      const params: Record<string, string> = {};
      const query = next.q ?? q;
      const target = next.page ?? 1;
      if (query) params.q = query;
      if (target > 1) params.page = String(target);
      router.get(VIEW_URL, params, { preserveState: true, preserveScroll: true });
    },
    [q],
  );

  // Debounced search — see settings' Browse page for the same pattern.
  useEffect(() => {
    if (search === q) return;
    const timeout = setTimeout(() => navigate({ q: search, page: 1 }), 300);
    return () => clearTimeout(timeout);
  }, [search, q, navigate]);

  function reload() {
    router.reload();
  }

  return (
    <>
      <Head title={t(keys.tenants.admin.head_title)} />
      <PageShell
        title={t(keys.tenants.admin.title)}
        description={t(keys.tenants.admin.description)}
      >
        <div className="mb-4 relative max-w-sm">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t(keys.tenants.admin.search_placeholder)}
            className="pl-9 max-lg:min-h-11"
          />
        </div>

        <Card className="overflow-hidden p-0">
          {tenants.length === 0 ? (
            <EmptyState
              icon={Building2}
              title={t(keys.tenants.admin.empty_title)}
              description={t(keys.tenants.admin.empty_description)}
            />
          ) : (
            <AdminTenantsTable tenants={tenants} onChanged={reload} />
          )}

          <div className="flex items-center justify-end gap-2 border-t px-4 py-3">
            <Button
              variant="outline"
              size="sm"
              className="max-lg:min-h-11"
              disabled={page <= 1}
              onClick={() => navigate({ page: page - 1 })}
            >
              {t(keys.tenants.admin.previous)}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="max-lg:min-h-11"
              disabled={!has_more}
              onClick={() => navigate({ page: page + 1 })}
            >
              {t(keys.tenants.admin.next)}
            </Button>
          </div>
        </Card>
      </PageShell>
    </>
  );
}

AdminBrowse.layout = [AdminLayout];
export default AdminBrowse;
