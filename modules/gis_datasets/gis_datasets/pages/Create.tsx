import { Link, router } from '@inertiajs/react';
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

const KINDS = [
  '',
  'vector_geojson',
  'vector_shapefile',
  'vector_kml',
  'raster_geotiff',
  'tabular_csv',
  'other',
];

function Create() {
  const { t } = useT();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [kind, setKind] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      toast.error(t(keys.gis_datasets.validation.file_required));
      return;
    }
    if (!name.trim()) {
      toast.error(t(keys.gis_datasets.validation.name_required));
      return;
    }
    const data = new FormData();
    data.append('name', name);
    if (description) data.append('description', description);
    if (kind) data.append('kind', kind);
    data.append('file', file);

    setSubmitting(true);
    router.post('/api/gis_datasets/', data, {
      forceFormData: true,
      onSuccess: () => toast.success(t(keys.gis_datasets.toasts.created)),
      onError: (errs) => {
        const first = Object.values(errs)[0];
        if (first) toast.error(String(first));
      },
      onFinish: () => setSubmitting(false),
    });
  }

  return (
    <PageShell
      title={t(keys.gis_datasets.create.title)}
      description={t(keys.gis_datasets.create.description)}
      actions={
        <Button asChild variant="outline">
          <Link href="/gis_datasets">{t(keys.gis_datasets.form.cancel_button)}</Link>
        </Button>
      }
    >
      <Card className="max-w-xl">
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="name">
                {t(keys.gis_datasets.form.name_label)} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t(keys.gis_datasets.form.name_placeholder)}
                maxLength={200}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="kind">{t(keys.gis_datasets.form.kind_label)}</Label>
              <select
                id="kind"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                {KINDS.map((k) => (
                  <option key={k || 'auto'} value={k}>
                    {k || t(keys.gis_datasets.form.kind_auto)}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="file">
                {t(keys.gis_datasets.form.file_label)} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="file"
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">{t(keys.gis_datasets.form.description_label)}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                placeholder={t(keys.gis_datasets.form.description_placeholder)}
                maxLength={2000}
              />
            </div>

            <div className="pt-2 flex gap-3">
              <Button type="submit" disabled={submitting}>
                {submitting
                  ? t(keys.gis_datasets.create.submitting_button)
                  : t(keys.gis_datasets.create.submit_button)}
              </Button>
              <Button asChild variant="outline">
                <Link href="/gis_datasets">{t(keys.gis_datasets.form.cancel_button)}</Link>
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}

Create.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Create;
