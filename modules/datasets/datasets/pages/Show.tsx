import { Link, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent } from '@simple-module/ui/components/ui/card';
import { usePermissions } from '@simple-module/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { Download, Pencil } from 'lucide-react';

interface Dataset {
  id: number;
  name: string;
  slug: string;
  kind: string;
  description: string | null;
  original_filename: string;
  mime_type: string | null;
  size_bytes: number;
  crs: string | null;
  bbox_min_x: number | null;
  bbox_min_y: number | null;
  bbox_max_x: number | null;
  bbox_max_y: number | null;
  feature_count: number | null;
  band_count: number | null;
  extraction_status: string;
  created_at: string | null;
}

interface Props {
  dataset: Dataset;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-4 py-2 border-b last:border-b-0">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="col-span-2 text-sm">{children}</dd>
    </div>
  );
}

function Show() {
  const { dataset } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const { can } = usePermissions();

  const bbox =
    dataset.bbox_min_x !== null &&
    dataset.bbox_min_y !== null &&
    dataset.bbox_max_x !== null &&
    dataset.bbox_max_y !== null
      ? `${dataset.bbox_min_x}, ${dataset.bbox_min_y}, ${dataset.bbox_max_x}, ${dataset.bbox_max_y}`
      : null;

  return (
    <PageShell
      title={dataset.name}
      description={dataset.description ?? undefined}
      actions={
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <a href={`/api/datasets/${dataset.id}/download`}>
              <Download />
              {t(keys.datasets.show.download)}
            </a>
          </Button>
          {can('datasets.edit') && (
            <Button asChild>
              <Link href={`/datasets/${dataset.id}/edit`}>
                <Pencil />
                {t(keys.datasets.show.edit)}
              </Link>
            </Button>
          )}
        </div>
      }
    >
      <Card className="max-w-3xl">
        <CardContent className="pt-6">
          <dl>
            <Row label={t(keys.datasets.show.kind)}>
              <Badge variant="secondary">{dataset.kind}</Badge>
            </Row>
            <Row label={t(keys.datasets.show.original_file)}>
              <span className="font-mono text-xs">{dataset.original_filename}</span>
            </Row>
            <Row label={t(keys.datasets.show.size)}>{dataset.size_bytes} bytes</Row>
            <Row label={t(keys.datasets.show.mime_type)}>{dataset.mime_type ?? '—'}</Row>
            <Row label={t(keys.datasets.show.crs)}>{dataset.crs ?? '—'}</Row>
            <Row label={t(keys.datasets.show.bbox)}>
              {bbox ? <span className="font-mono text-xs">{bbox}</span> : '—'}
            </Row>
            {dataset.feature_count !== null && (
              <Row label={t(keys.datasets.show.features)}>{dataset.feature_count}</Row>
            )}
            {dataset.band_count !== null && (
              <Row label={t(keys.datasets.show.bands)}>{dataset.band_count}</Row>
            )}
            <Row label={t(keys.datasets.show.extraction_status)}>
              <Badge>{dataset.extraction_status}</Badge>
            </Row>
          </dl>
        </CardContent>
      </Card>
    </PageShell>
  );
}

Show.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Show;
