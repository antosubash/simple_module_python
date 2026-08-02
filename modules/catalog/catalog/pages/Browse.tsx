import { Head, Link, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Package } from 'lucide-react';
import type React from 'react';
import { useState } from 'react';

type ProductStatus = 'draft' | 'active' | 'archived';

interface ProductRead {
  id: string;
  sku: string;
  name: string;
  description: string;
  status: ProductStatus;
  price_cents: number;
  category_id: string;
  created_at: string;
}

interface Props {
  items: ProductRead[];
  total: number;
  page: number;
  page_size: number;
  categories: { id: string; name: string; slug: string }[];
  filters: { q: string | null; status: string | null; sort: string };
}

const STATUS_BADGE: Record<ProductStatus, string> = {
  draft: 'border-slate-200 bg-slate-50 text-slate-700',
  active: 'border-green-200 bg-green-50 text-green-700',
  archived: 'border-amber-200 bg-amber-50 text-amber-700',
};
const TH = 'sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground';

function formatPrice(cents: number): string {
  return (cents / 100).toFixed(2);
}

function Browse() {
  const { items, total, page, page_size, filters } = usePage<{ props: Props }>()
    .props as unknown as Props;
  const { t } = useT();
  const [query, setQuery] = useState(filters.q ?? '');

  function navigate(nextQuery: string, nextPage = 1) {
    const params: Record<string, string> = {};
    if (nextQuery) params.q = nextQuery;
    if (filters.status) params.status = filters.status;
    if (filters.sort) params.sort = filters.sort;
    if (nextPage > 1) params.page = String(nextPage);
    // GET against the view route, not /api/* — Inertia rejects non-Inertia
    // responses (see SM018).
    router.get(`/catalog/?${new URLSearchParams(params).toString()}`);
  }

  const totalPages = Math.max(1, Math.ceil(total / page_size));

  return (
    <>
      <Head title="Catalog" />
      <PageShell
        title={t(keys.catalog.browse.title)}
        description={t(keys.catalog.browse.description)}
      >
        <form
          className="mb-4 flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            navigate(query);
          }}
        >
          <Input
            aria-label={t(keys.catalog.browse.search_label)}
            placeholder={t(keys.catalog.browse.search_placeholder)}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="max-w-xs"
          />
          <Button type="submit" variant="outline" size="sm">
            {t(keys.catalog.browse.search_button)}
          </Button>
        </form>

        {items.length === 0 ? (
          <Card className="border-border">
            <div className="flex flex-col items-center gap-2 py-16 text-muted-foreground">
              <Package className="size-8" />
              <h2 className="text-base font-semibold text-foreground font-[var(--font-display)]">
                {t(keys.catalog.browse.empty_title)}
              </h2>
              <p className="text-sm">{t(keys.catalog.browse.empty_description)}</p>
            </div>
          </Card>
        ) : (
          <Card className="border-border overflow-hidden p-0">
            <Table>
              <TableHeader className="bg-secondary/40">
                <TableRow>
                  <TableHead className={TH}>{t(keys.catalog.columns.sku)}</TableHead>
                  <TableHead className={TH}>{t(keys.catalog.columns.name)}</TableHead>
                  <TableHead className={TH}>{t(keys.catalog.columns.status)}</TableHead>
                  <TableHead className={`${TH} hidden sm:table-cell`}>
                    {t(keys.catalog.columns.price)}
                  </TableHead>
                  <TableHead className={`${TH} hidden md:table-cell`}>
                    {t(keys.catalog.columns.created)}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((product) => (
                  <TableRow key={product.id} className="hover:bg-secondary/40">
                    <TableCell className="sm:px-6 font-mono text-xs text-muted-foreground">
                      {product.sku}
                    </TableCell>
                    <TableCell className="sm:px-6">
                      <Link
                        href={`/catalog/${product.id}`}
                        data-testid="catalog-row"
                        className="font-medium text-sm hover:underline"
                      >
                        {product.name}
                      </Link>
                    </TableCell>
                    <TableCell className="sm:px-6">
                      <Badge variant="outline" className={STATUS_BADGE[product.status] ?? ''}>
                        {t(keys.catalog.status[product.status])}
                      </Badge>
                    </TableCell>
                    <TableCell className="sm:px-6 hidden sm:table-cell text-sm tabular-nums">
                      {formatPrice(product.price_cents)}
                    </TableCell>
                    <TableCell className="sm:px-6 hidden md:table-cell text-sm tabular-nums text-muted-foreground">
                      {new Date(product.created_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}

        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {t(keys.catalog.browse.showing, { page, pages: totalPages, total })}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => navigate(query, page - 1)}
              >
                {t(keys.catalog.browse.previous)}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => navigate(query, page + 1)}
              >
                {t(keys.catalog.browse.next)}
              </Button>
            </div>
          </div>
        )}
      </PageShell>
    </>
  );
}

Browse.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Browse;
