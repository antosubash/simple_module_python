import { Link, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent } from '@simple-module/ui/components/ui/card';
import { Input } from '@simple-module/ui/components/ui/input';
import { Label } from '@simple-module/ui/components/ui/label';
import { Textarea } from '@simple-module/ui/components/ui/textarea';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { useState } from 'react';
import { toast } from 'sonner';

interface Dataset {
  id: number;
  name: string;
  kind: string;
  description: string | null;
  crs: string | null;
}

interface Props {
  dataset: Dataset;
}

const KINDS = [
  'vector_geojson',
  'vector_shapefile',
  'vector_kml',
  'raster_geotiff',
  'tabular_csv',
  'other',
];

function Edit() {
  const { dataset } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const [name, setName] = useState(dataset.name);
  const [description, setDescription] = useState(dataset.description ?? '');
  const [kind, setKind] = useState(dataset.kind);
  const [crs, setCrs] = useState(dataset.crs ?? '');
  const [submitting, setSubmitting] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    router.patch(
      `/api/datasets/${dataset.id}`,
      { name, description: description || null, kind, crs: crs || null },
      {
        onSuccess: () => {
          toast.success(t(keys.datasets.toasts.updated));
          router.visit('/datasets');
        },
        onError: (errs) => {
          const first = Object.values(errs)[0];
          if (first) toast.error(String(first));
        },
        onFinish: () => setSubmitting(false),
      },
    );
  }

  return (
    <PageShell
      title={t(keys.datasets.edit.title, { name: dataset.name })}
      description={t(keys.datasets.edit.description)}
      actions={
        <Button asChild variant="outline">
          <Link href="/datasets">{t(keys.datasets.edit.back_button)}</Link>
        </Button>
      }
    >
      <Card className="max-w-xl">
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="name">
                {t(keys.datasets.form.name_label)} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={200}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="kind">{t(keys.datasets.form.kind_label)}</Label>
              <select
                id="kind"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="crs">{t(keys.datasets.form.crs_label)}</Label>
              <Input
                id="crs"
                value={crs}
                onChange={(e) => setCrs(e.target.value)}
                placeholder="EPSG:4326"
                maxLength={64}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">{t(keys.datasets.form.description_label)}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                maxLength={2000}
              />
            </div>

            <div className="pt-2 flex gap-3">
              <Button type="submit" disabled={submitting}>
                {submitting
                  ? t(keys.datasets.edit.submitting_button)
                  : t(keys.datasets.edit.submit_button)}
              </Button>
              <Button asChild variant="outline">
                <Link href="/datasets">{t(keys.datasets.form.cancel_button)}</Link>
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}

Edit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Edit;
