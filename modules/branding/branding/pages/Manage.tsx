import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import type { SharedProps } from '@simple-module-py/ui/types';
import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { BannerField, type BannerSeverity } from '../components/BannerField';
import { DesignPackField, type DesignPackOption } from '../components/DesignPackField';
import { type BrandingForm, countBrandingChanges } from '../components/dirty';
import { FooterLinksField } from '../components/FooterLinksField';
import { ImageDropzones, type ImageKind } from '../components/ImageDropzones';
import { PresetField, type PresetOption } from '../components/PresetField';
import { PreviewTabs } from '../components/PreviewTabs';

/** Matches `BUILTIN_PRESETS[0]` in `branding/presets.py`. */
const DEFAULT_SWATCH = '#0f766e';
/** Mirrors `DEFAULT_APP_NAME` in `branding/settings.py`. */
const DEFAULT_APP_NAME = 'SimpleModule';
/** Mirrors `MAX_APP_NAME_LEN` in `branding/constants.py`. */
const MAX_APP_NAME = 60;

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
  // ``designPacks`` and ``presets`` are page props, not shared ones: the
  // choices depend on which modules the host has installed, so only the view
  // can supply them.
  const page = usePage<{ props: SharedProps }>().props as unknown as SharedProps & {
    designPacks?: DesignPackOption[];
    presets?: PresetOption[];
  };
  const { auth, branding } = page;
  const canManage = auth?.permissions?.includes('branding.manage');

  // What the server currently holds. Recomputed whenever an Inertia visit
  // brings fresh props, which is how the dirty count falls back to zero after
  // a successful publish without any explicit reset.
  const baseline = useMemo<BrandingForm>(
    () => ({
      appName: branding?.appName ?? '',
      color: branding?.primaryColor ?? '',
      designPack: branding?.designPack ?? '',
      bannerMessage: branding?.banner?.message ?? '',
      bannerSeverity: (branding?.banner?.severity as BannerSeverity) ?? 'info',
      footerLinks: branding?.footerLinks ?? [],
    }),
    [branding],
  );

  const [form, setForm] = useState<BrandingForm>(baseline);
  const [busy, setBusy] = useState(false);
  const changes = countBrandingChanges(form, baseline);
  const locked = !canManage || busy;

  const set = (patch: Partial<BrandingForm>) => setForm((current) => ({ ...current, ...patch }));

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

  const publish = () =>
    run(
      () =>
        fetch('/api/branding/', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            app_name: form.appName,
            primary_color: form.color,
            design_pack: form.designPack,
            banner_message: form.bannerMessage,
            banner_severity: form.bannerSeverity,
            footer_links: form.footerLinks,
          }),
        }),
      t(keys.branding.manage.error_toast),
    );

  const uploadImage = (kind: ImageKind, file: File) => {
    const body = new FormData();
    body.append('file', file);
    return run(
      () => fetch(`/api/branding/${kind}`, { method: 'POST', body }),
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
        actions={
          <>
            {changes > 0 && (
              <span className="text-[13px] text-amber-700">
                {t(keys.branding.manage.unsaved_changes, { count: changes })}
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={locked || changes === 0}
              onClick={() => setForm(baseline)}
            >
              {t(keys.branding.manage.discard)}
            </Button>
            <Button size="sm" disabled={locked} onClick={publish}>
              {busy ? t(keys.branding.manage.publishing) : t(keys.branding.manage.publish)}
            </Button>
          </>
        }
      >
        <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
          <Card className="border-border">
            <CardContent className="flex flex-col gap-4 pt-5">
              <div className="grid gap-3.5 sm:grid-cols-2">
                <div className="flex flex-col gap-2">
                  <Label
                    htmlFor="app_name"
                    className="text-[12.5px] font-medium text-muted-foreground"
                  >
                    {t(keys.branding.manage.app_name_label)}
                  </Label>
                  <Input
                    id="app_name"
                    value={form.appName}
                    maxLength={MAX_APP_NAME}
                    disabled={locked}
                    onChange={(e) => set({ appName: e.target.value })}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label
                    htmlFor="primary_color"
                    className="text-[12.5px] font-medium text-muted-foreground"
                  >
                    {t(keys.branding.manage.primary_color_label)}
                  </Label>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      aria-label={t(keys.branding.manage.primary_color_label)}
                      value={form.color || DEFAULT_SWATCH}
                      disabled={locked}
                      onChange={(e) => set({ color: e.target.value })}
                      className="h-9 w-9 shrink-0 cursor-pointer rounded-[9px] border bg-transparent"
                    />
                    <Input
                      id="primary_color"
                      value={form.color}
                      placeholder={DEFAULT_SWATCH}
                      disabled={locked}
                      onChange={(e) => set({ color: e.target.value })}
                      className="min-w-0 flex-1 font-mono"
                    />
                  </div>
                </div>
              </div>

              <PresetField
                options={page.presets ?? []}
                activeColor={form.color}
                onSelect={(swatch) => set({ color: swatch })}
                disabled={locked}
              />

              <BannerField
                message={form.bannerMessage}
                severity={form.bannerSeverity}
                onMessageChange={(bannerMessage) => set({ bannerMessage })}
                onSeverityChange={(bannerSeverity) => set({ bannerSeverity })}
                disabled={locked}
              />

              <ImageDropzones
                logoUrl={branding?.logoUrl ?? null}
                logoDarkUrl={branding?.logoDarkUrl ?? null}
                faviconUrl={branding?.faviconUrl ?? null}
                onUpload={uploadImage}
                onRemove={removeImage}
                disabled={locked}
              />

              <FooterLinksField
                links={form.footerLinks}
                onChange={(footerLinks) => set({ footerLinks })}
                disabled={locked}
              />

              <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3.5">
                <span className="text-[12.5px] text-muted-foreground">
                  {t(keys.branding.manage.publish_note)}
                </span>
                <DesignPackField
                  options={page.designPacks ?? []}
                  value={form.designPack}
                  onChange={(designPack) => set({ designPack })}
                  disabled={locked}
                />
              </div>
            </CardContent>
          </Card>

          <PreviewTabs
            brand={{
              appName: form.appName || DEFAULT_APP_NAME,
              accent: form.color || DEFAULT_SWATCH,
              logoUrl: branding?.logoUrl ?? null,
              logoDarkUrl: branding?.logoDarkUrl ?? null,
              bannerMessage: form.bannerMessage,
              footerLinks: form.footerLinks,
              menuLabels: (page.menus?.sidebar ?? []).map((item) => item.label),
            }}
          />
        </div>
      </PageShell>
    </>
  );
}

Manage.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;

export default Manage;
