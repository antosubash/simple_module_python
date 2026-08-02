import { Head, Link, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import type React from 'react';

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
  product: ProductRead;
}

const STATUS_BADGE: Record<ProductStatus, string> = {
  draft: 'border-slate-200 bg-slate-50 text-slate-700',
  active: 'border-green-200 bg-green-50 text-green-700',
  archived: 'border-amber-200 bg-amber-50 text-amber-700',
};
const DT = 'text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground';

function Detail() {
  const { product } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  return (
    <>
      <Head title={product.name} />
      <PageShell title={product.name} description={t(keys.catalog.detail.title)}>
        <Link
          href="/catalog/"
          data-testid="catalog-back"
          className="text-sm text-primary hover:underline"
        >
          {t(keys.catalog.detail.back_link)}
        </Link>

        <Card className="border-border mt-4 p-6">
          <dl className="grid gap-4 sm:grid-cols-2">
            <div>
              <dt className={DT}>{t(keys.catalog.columns.sku)}</dt>
              <dd className="font-mono text-sm">{product.sku}</dd>
            </div>
            <div>
              <dt className={DT}>{t(keys.catalog.columns.status)}</dt>
              <dd>
                <Badge variant="outline" className={STATUS_BADGE[product.status] ?? ''}>
                  {t(keys.catalog.status[product.status])}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className={DT}>{t(keys.catalog.columns.price)}</dt>
              <dd className="text-sm tabular-nums">{(product.price_cents / 100).toFixed(2)}</dd>
            </div>
            <div>
              <dt className={DT}>{t(keys.catalog.columns.created)}</dt>
              <dd className="text-sm tabular-nums text-muted-foreground">
                {new Date(product.created_at).toLocaleString()}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className={DT}>{t(keys.catalog.detail.description_label)}</dt>
              <dd className="text-sm">{product.description}</dd>
            </div>
          </dl>
        </Card>
      </PageShell>
    </>
  );
}

Detail.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Detail;
