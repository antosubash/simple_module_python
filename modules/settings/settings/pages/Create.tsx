import { Head, Link, useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import { Textarea } from '@simple-module-py/ui/components/ui/textarea';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import type React from 'react';
import { KeyField, type KnownKey } from './components/KeyField';
import ValueInput, { VALUE_TYPES, type ValueType } from './components/ValueInput';
import { ROUTES } from './routes';

const SCOPES = ['system', 'tenant', 'user'] as const;
type Scope = (typeof SCOPES)[number];

type Props = { known_keys?: KnownKey[] };

function Create({ known_keys }: Props) {
  const { t } = useT();
  const { data, setData, post, processing, errors } = useForm({
    scope: 'system' as Scope,
    scope_id: '',
    key: '',
    value_type: 'string' as ValueType,
    value: '',
    description: '',
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    post(ROUTES.browse);
  }

  return (
    <>
      <Head title={t(keys.settings.create.head_title)} />
      <PageShell
        title={t(keys.settings.create.title)}
        actions={
          <Button asChild variant="outline">
            <Link href={ROUTES.browse}>{t(keys.settings.form.cancel_button)}</Link>
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
                <Select value={data.scope} onValueChange={(v) => setData('scope', v as Scope)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SCOPES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {t(keys.settings.scopes[s])}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {errors.scope && <p className="text-xs text-destructive">{errors.scope}</p>}
              </div>

              <div className="space-y-2">
                <Label className="text-sm font-medium text-muted-foreground">
                  {t(keys.settings.form.scope_id_label)}
                </Label>
                <Input
                  value={data.scope_id}
                  onChange={(e) => setData('scope_id', e.target.value)}
                  placeholder={t(keys.settings.form.scope_id_placeholder)}
                  className="font-mono"
                />
                {errors.scope_id && <p className="text-xs text-destructive">{errors.scope_id}</p>}
              </div>

              <KeyField
                value={data.key}
                knownKeys={known_keys ?? []}
                error={errors.key}
                onChange={(key, type) => {
                  setData((prev) => ({
                    ...prev,
                    key,
                    ...(type ? { value_type: type as ValueType } : {}),
                  }));
                }}
              />

              <div className="space-y-2">
                <Label className="text-sm font-medium text-muted-foreground">
                  {t(keys.settings.form.value_type_label)}
                </Label>
                <Select
                  value={data.value_type}
                  onValueChange={(v) => setData('value_type', v as ValueType)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {VALUE_TYPES.map((vt) => (
                      <SelectItem key={vt} value={vt}>
                        {t(keys.settings.value_types[vt])}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
                  placeholder={t(keys.settings.form.description_placeholder)}
                />
              </div>

              <div className="sm:col-span-2 flex justify-end gap-2">
                <Button asChild variant="outline">
                  <Link href={ROUTES.browse}>{t(keys.settings.form.cancel_button)}</Link>
                </Button>
                <Button type="submit" disabled={processing}>
                  {t(keys.settings.create.submit_button)}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </PageShell>
    </>
  );
}

Create.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Create;
