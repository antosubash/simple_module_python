import { Link, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from '@simple-module-py/ui/components/ui/empty';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Layers, Plus, Trash2 } from 'lucide-react';

interface Dataset {
  id: number;
  name: string;
  slug: string;
  kind: string;
  size_bytes: number;
  crs: string | null;
  bbox_min_x: number | null;
  bbox_min_y: number | null;
  bbox_max_x: number | null;
  bbox_max_y: number | null;
  extraction_status: string;
  created_at: string | null;
}

interface Props {
  datasets: Dataset[];
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatBbox(d: Dataset): string {
  if (
    d.bbox_min_x === null ||
    d.bbox_min_y === null ||
    d.bbox_max_x === null ||
    d.bbox_max_y === null
  ) {
    return '—';
  }
  return `[${d.bbox_min_x.toFixed(3)}, ${d.bbox_min_y.toFixed(3)}, ${d.bbox_max_x.toFixed(3)}, ${d.bbox_max_y.toFixed(3)}]`;
}

function Browse() {
  const { datasets } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const { can } = usePermissions();
  const canUpload = can('datasets.upload');
  const canDelete = can('datasets.delete');

  function handleDelete(dataset: Dataset) {
    router.delete(`/api/datasets/${dataset.id}`, { preserveScroll: true });
  }

  return (
    <PageShell
      title={t(keys.datasets.browse.title)}
      description={t(keys.datasets.browse.description)}
      actions={
        canUpload ? (
          <Button asChild>
            <Link href="/datasets/create">
              <Plus />
              {t(keys.datasets.browse.new_button)}
            </Link>
          </Button>
        ) : undefined
      }
    >
      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="sm:px-6">{t(keys.datasets.table.name)}</TableHead>
              <TableHead className="sm:px-6">{t(keys.datasets.table.kind)}</TableHead>
              <TableHead className="hidden md:table-cell sm:px-6">
                {t(keys.datasets.table.crs)}
              </TableHead>
              <TableHead className="hidden md:table-cell sm:px-6">
                {t(keys.datasets.table.bbox)}
              </TableHead>
              <TableHead className="sm:px-6">{t(keys.datasets.table.size)}</TableHead>
              <TableHead className="text-right sm:px-6">{t(keys.datasets.table.actions)}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {datasets.map((dataset) => (
              <TableRow key={dataset.id}>
                <TableCell className="sm:px-6">
                  <Link href={`/datasets/${dataset.id}`} className="font-medium hover:underline">
                    {dataset.name}
                  </Link>
                </TableCell>
                <TableCell className="sm:px-6">
                  <Badge variant="secondary">{dataset.kind}</Badge>
                </TableCell>
                <TableCell className="hidden md:table-cell sm:px-6 text-muted-foreground text-sm">
                  {dataset.crs || '—'}
                </TableCell>
                <TableCell className="hidden md:table-cell sm:px-6 text-xs text-muted-foreground tabular-nums">
                  {formatBbox(dataset)}
                </TableCell>
                <TableCell className="sm:px-6 tabular-nums text-muted-foreground">
                  {formatBytes(dataset.size_bytes)}
                </TableCell>
                <TableCell className="text-right sm:px-6">
                  {canDelete && (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => handleDelete(dataset)}
                    >
                      <Trash2 />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {datasets.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="h-40">
                  <Empty>
                    <EmptyMedia variant="icon">
                      <Layers className="size-5 text-primary-300" />
                    </EmptyMedia>
                    <EmptyTitle>{t(keys.datasets.browse.empty_title)}</EmptyTitle>
                    <EmptyDescription>{t(keys.datasets.browse.empty_description)}</EmptyDescription>
                    {canUpload && (
                      <Button asChild size="sm" className="mt-2">
                        <Link href="/datasets/create">{t(keys.datasets.browse.create_button)}</Link>
                      </Button>
                    )}
                  </Empty>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </PageShell>
  );
}

Browse.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Browse;
