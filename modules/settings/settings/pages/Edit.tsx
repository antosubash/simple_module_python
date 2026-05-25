import { Head, Link, useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { Textarea } from '@simple-module-py/ui/components/ui/textarea';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import type React from 'react';
import ValueInput, { type ValueType } from './components/ValueInput';
import { ROUTES } from './routes';

type Scope = 'system' | 'tenant' | 'user';

type Setting = {
  id: number;
  scope: Scope;
  scope_id: string;
  key: string;
  value: string;
  value_type: ValueType;
  description: string | null;
};

type Props = { setting: Setting };

function Edit({ setting }: Props) {
  const { t } = useT();
  const { data, setData, put, processing, errors } = useForm({
    value: setting.value,
    value_type: setting.value_type,
    description: setting.description ?? '',
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    put(ROUTES.byId(setting.id));
  }

  return (
    <>
      <Head title="Edit Setting" />
      <PageShell
        title={t(keys.settings.edit.title)}
      description={`${setting.scope}.${setting.key}`}
      actions={
        <Button asChild variant="outline">
          <Link href={ROUTES.browse}>Cancel</Link>
        </Button>
      }
    >
      <Card className="max-w-2xl border-border">
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label className="text-sm font-medium text-muted-foreground">
                {t(keys.settings.form.scope_label)}
              </Label>
              <Input value={t(keys.settings.scopes[setting.scope])} disabled className="bg-muted" />
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-medium text-muted-foreground">
                {t(keys.settings.form.scope_id_label)}
              </Label>
              <Input value={setting.scope_id || '—'} disabled className="bg-muted font-mono" />
            </div>

            <div className="space-y-2 sm:col-span-2">
              <Label className="text-sm font-medium text-muted-foreground">
                {t(keys.settings.form.key_label)}
              </Label>
              <Input defaultValue={setting.key} disabled className="bg-muted font-mono" />
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-medium text-muted-foreground">
                {t(keys.settings.form.value_type_label)}
              </Label>
              <Input
                value={t(keys.settings.value_types[setting.value_type])}
                disabled
                className="bg-muted"
              />
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-medium text-muted-foreground">
                {t(keys.settings.form.value_label)}
              </Label>
              <ValueInput
                valueType={data.value_type}
                value={data.value}
                onValueChange={(v) => setData('value', v)}
                required
              />
              {errors.value && <p className="text-xs text-destructive">{errors.value}</p>}
            </div>

            <div className="space-y-2 sm:col-span-2">
              <Label className="text-sm font-medium text-muted-foreground">
                {t(keys.settings.form.description_label)}
              </Label>
              <Textarea
                value={data.description}
                onChange={(e) => setData('description', e.target.value)}
              />
            </div>

            <div className="sm:col-span-2 flex justify-end gap-2">
              <Button asChild variant="outline">
                <Link href={ROUTES.browse}>Cancel</Link>
              </Button>
              <Button type="submit" disabled={processing}>
                {t(keys.settings.edit.submit_button)}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </PageShell>
    </>
  );
}

Edit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Edit;
