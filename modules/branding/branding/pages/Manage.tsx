import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import type { SharedProps } from '@simple-module-py/ui/types';
import { useState } from 'react';
import { toast } from 'sonner';
import { DesignPackField, type DesignPackOption } from '../components/DesignPackField';
import { ImageField } from '../components/ImageField';

const DEFAULT_SWATCH = '#10b981';
/** Matches the upload/clear route segments under `/api/branding/`. */
type ImageKind = 'logo' | 'logo-dark' | 'favicon';

/** The sidebar is near-black, so preview the dark variant against it. */
const DARK_PREVIEW = 'bg-app-sidebar';

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === 'string' ? body.detail : res.statusText;
  } catch {
    return res.statusText;
  }
}

function Manage() {
  const { t } = useT();
  // ``designPacks`` is a page prop, not a shared one: the choices depend on
  // which modules the host has installed, so only the view can supply them.
  const page = usePage<{ props: SharedProps }>().props as unknown as SharedProps & {
    designPacks?: DesignPackOption[];
  };
  const { auth, branding } = page;
  const canManage = auth?.permissions?.includes('branding.manage');

  const [appName, setAppName] = useState(branding?.appName ?? '');
  const [color, setColor] = useState(branding?.primaryColor ?? '');
  const [designPack, setDesignPack] = useState(branding?.designPack ?? '');
  const [busy, setBusy] = useState(false);

  async function run(work: () => Promise<Response>, errorMsg: string) {
    setBusy(true);
    try {
      const res = await work();
      if (!res.ok) throw new Error(await readError(res));
      toast.success(t(keys.branding.manage.saved_toast));
      router.reload();
    } catch (err) {
      toast.error(`${errorMsg}: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  const saveText = () =>
    run(
      () =>
        fetch('/api/branding/', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            app_name: appName,
            primary_color: color,
            design_pack: designPack,
          }),
        }),
      t(keys.branding.manage.error_toast),
    );

  const uploadImage = (kind: ImageKind, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return run(
      () => fetch(`/api/branding/${kind}`, { method: 'POST', body: form }),
      t(keys.branding.manage.upload_error_toast),
    );
  };

  const removeImage = (kind: ImageKind) =>
    run(
      () => fetch(`/api/branding/${kind}`, { method: 'DELETE' }),
      t(keys.branding.manage.error_toast),
    );

  return (
    <>
      <Head title={t(keys.branding.manage.title)} />
      <PageShell
        title={t(keys.branding.manage.title)}
        description={t(keys.branding.manage.description)}
      >
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>{t(keys.branding.manage.title)}</CardTitle>
              <CardDescription>{t(keys.branding.manage.description)}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="app_name">{t(keys.branding.manage.app_name_label)}</Label>
                <Input
                  id="app_name"
                  value={appName}
                  maxLength={60}
                  disabled={!canManage || busy}
                  onChange={(e) => setAppName(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  {t(keys.branding.manage.app_name_help)}
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="primary_color">{t(keys.branding.manage.primary_color_label)}</Label>
                <div className="flex items-center gap-3">
                  <input
                    type="color"
                    aria-label={t(keys.branding.manage.primary_color_label)}
                    value={color || DEFAULT_SWATCH}
                    disabled={!canManage || busy}
                    onChange={(e) => setColor(e.target.value)}
                    className="h-9 w-12 cursor-pointer rounded border bg-transparent"
                  />
                  <Input
                    id="primary_color"
                    value={color}
                    placeholder={DEFAULT_SWATCH}
                    disabled={!canManage || busy}
                    onChange={(e) => setColor(e.target.value)}
                    className="max-w-40 font-mono"
                  />
                  {color && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={busy}
                      onClick={() => setColor('')}
                    >
                      {t(keys.branding.manage.remove_button)}
                    </Button>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {t(keys.branding.manage.primary_color_help)}
                </p>
              </div>

              <DesignPackField
                options={page.designPacks ?? []}
                value={designPack}
                onChange={setDesignPack}
                disabled={!canManage || busy}
              />

              <ImageField
                label={t(keys.branding.manage.logo_label)}
                help={t(keys.branding.manage.logo_help)}
                url={branding?.logoUrl ?? null}
                onUpload={(file) => uploadImage('logo', file)}
                onRemove={() => removeImage('logo')}
                disabled={!canManage || busy}
              />
              <ImageField
                label={t(keys.branding.manage.logo_dark_label)}
                help={t(keys.branding.manage.logo_dark_help)}
                url={branding?.logoDarkUrl ?? null}
                onUpload={(file) => uploadImage('logo-dark', file)}
                onRemove={() => removeImage('logo-dark')}
                disabled={!canManage || busy}
                previewClassName={DARK_PREVIEW}
              />
              <ImageField
                label={t(keys.branding.manage.favicon_label)}
                help={t(keys.branding.manage.favicon_help)}
                url={branding?.faviconUrl ?? null}
                onUpload={(file) => uploadImage('favicon', file)}
                onRemove={() => removeImage('favicon')}
                disabled={!canManage || busy}
              />

              <Button type="button" disabled={!canManage || busy} onClick={saveText}>
                {busy ? t(keys.branding.manage.saving) : t(keys.branding.manage.save_button)}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t(keys.branding.manage.preview_title)}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3 rounded-lg border p-4">
                <div
                  className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-lg text-white"
                  style={{ backgroundColor: color || DEFAULT_SWATCH }}
                >
                  {branding?.logoUrl ? (
                    <img
                      src={branding.logoUrl}
                      alt={appName}
                      className="h-full w-full object-contain"
                    />
                  ) : (
                    <span className="font-bold">{(appName.trim()[0] ?? 'S').toUpperCase()}</span>
                  )}
                </div>
                <span className="font-semibold">{appName || 'SimpleModule'}</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </PageShell>
    </>
  );
}

Manage.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;

export default Manage;
