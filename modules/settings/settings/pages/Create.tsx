import { Head, Link, useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
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
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import type React from 'react';
import { KeyField, type KnownKey } from './components/KeyField';
import { ResolvedValue } from './components/ResolvedValue';
import ValueInput from './components/ValueInput';
import { ROUTES } from './routes';
import { SCOPES, type SettingScope, VALUE_TYPES, type ValueType } from './types';

type Props = { known_keys?: KnownKey[] };

const LABEL = 'text-[12.5px] font-medium text-muted-foreground';

function Create({ known_keys }: Props) {
  const { t } = useT();
  const { data, setData, post, processing, errors } = useForm({
    scope: 'system' as SettingScope,
    scope_id: '',
    key: '',
    value_type: 'string' as ValueType,
    value: '',
    description: '',
  });

  const known = (known_keys ?? []).find((k) => k.key === data.key.trim());

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    post(ROUTES.browse);
  }

  return (
    <>
      <Head title={t(keys.settings.create.head_title)} />
      <PageShell
        title={t(keys.settings.create.title)}
        description={t(keys.settings.create.description)}
      >
        <div className="grid items-start gap-4 lg:grid-cols-[1.3fr_1fr]">
          <Card className="border-border p-6">
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="grid gap-3.5 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label className={LABEL}>{t(keys.settings.form.scope_label)}</Label>
                  <Select
                    value={data.scope}
                    onValueChange={(v) => setData('scope', v as SettingScope)}
                  >
                    <SelectTrigger className="w-full">
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

                <div className="space-y-1.5">
                  <Label className={LABEL}>{t(keys.settings.form.scope_id_label)}</Label>
                  <Input
                    value={data.scope_id}
                    onChange={(e) => setData('scope_id', e.target.value)}
                    placeholder={t(keys.settings.form.scope_id_placeholder)}
                    className="font-mono"
                  />
                  {errors.scope_id && <p className="text-xs text-destructive">{errors.scope_id}</p>}
                </div>
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

              <div className="grid gap-3.5 sm:grid-cols-[150px_1fr]">
                <div className="space-y-1.5">
                  <Label className={LABEL}>{t(keys.settings.form.value_type_label)}</Label>
                  <Select
                    value={data.value_type}
                    onValueChange={(v) => setData('value_type', v as ValueType)}
                  >
                    <SelectTrigger className="w-full">
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

                <div className="space-y-1.5">
                  <Label className={LABEL}>{t(keys.settings.form.value_label)}</Label>
                  <ValueInput
                    valueType={data.value_type}
                    value={data.value}
                    onValueChange={(v) => setData('value', v)}
                    required
                  />
                  {errors.value && <p className="text-xs text-destructive">{errors.value}</p>}
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className={LABEL}>{t(keys.settings.form.description_label)}</Label>
                <Textarea
                  value={data.description}
                  onChange={(e) => setData('description', e.target.value)}
                  placeholder={t(keys.settings.form.description_placeholder)}
                  rows={2}
                />
              </div>

              <div className="flex justify-end gap-2.5">
                <Button asChild variant="outline" className="max-lg:min-h-11">
                  <Link href={ROUTES.browse}>{t(keys.settings.form.cancel_button)}</Link>
                </Button>
                <Button type="submit" disabled={processing} className="max-lg:min-h-11">
                  {t(keys.settings.create.submit_button)}
                </Button>
              </div>
            </form>
          </Card>

          <ResolvedValue draft={data.value} known={known} />
        </div>
      </PageShell>
    </>
  );
}

Create.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Create;
