import { keys, useT } from '@simple-module-py/i18n';
import { type PreviewBrand, previewFooterLinks } from './BrandingPreview';

function Logo({ brand }: { brand: PreviewBrand }) {
  return brand.logoUrl ? (
    <img src={brand.logoUrl} alt={brand.appName} className="h-6 w-6 rounded object-contain" />
  ) : (
    <span
      aria-hidden="true"
      className="h-6 w-6 rounded"
      style={{ backgroundColor: brand.accent }}
    />
  );
}

/**
 * The sign-in card — the one branded surface an anonymous visitor sees.
 *
 * Worth its own tab because it is also the surface most easily broken by a
 * brand colour: the primary button sits on white, where a light swatch that
 * looked fine in the sidebar becomes unreadable.
 */
export function SignInPreview({ brand }: { brand: PreviewBrand }) {
  const { t } = useT();
  return (
    <div className="flex min-h-52 flex-1 flex-col items-center justify-center gap-3 rounded-[10px] border border-border bg-background p-4">
      <div className="w-full max-w-56 rounded-lg border border-border bg-card p-3.5">
        <div className="flex items-center gap-2">
          <Logo brand={brand} />
          <span className="truncate text-[11px] font-bold font-display">{brand.appName}</span>
        </div>
        <div className="mt-3 text-[11px] font-semibold">
          {t(keys.branding.manage.preview_signin_heading)}
        </div>
        <div className="mt-2 h-6 rounded border border-border bg-background" />
        <div className="mt-1.5 h-6 rounded border border-border bg-background" />
        <div
          className="mt-2.5 flex h-6 items-center justify-center rounded text-[9px] font-semibold text-white"
          style={{ backgroundColor: brand.accent }}
        >
          {t(keys.branding.manage.preview_signin_action)}
        </div>
      </div>
      <div className="text-[8px] text-muted-foreground">
        {previewFooterLinks(brand)
          .map((link) => link.label)
          .join(' · ')}
      </div>
    </div>
  );
}

/**
 * A transactional email header. The brand colour and the app name are what
 * carry over into mail; nothing else on this page reaches an inbox.
 */
export function EmailPreview({ brand }: { brand: PreviewBrand }) {
  const { t } = useT();
  return (
    <div className="flex min-h-52 flex-1 flex-col overflow-hidden rounded-[10px] border border-border bg-background">
      <div
        className="flex items-center gap-2 px-3 py-2.5"
        style={{ backgroundColor: brand.accent }}
      >
        <span className="truncate text-[11px] font-bold text-white font-display">
          {brand.appName}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3.5">
        <div className="text-[11px] font-semibold">
          {t(keys.branding.manage.preview_email_subject)}
        </div>
        <div className="h-2 w-full rounded bg-secondary" />
        <div className="h-2 w-4/5 rounded bg-secondary" />
        <div
          className="mt-1 flex h-6 w-32 items-center justify-center rounded text-[9px] font-semibold text-white"
          style={{ backgroundColor: brand.accent }}
        >
          {t(keys.branding.manage.preview_email_action)}
        </div>
      </div>
      <div className="border-t border-border px-3.5 py-1.5 text-[8px] text-muted-foreground">
        {brand.appName}
      </div>
    </div>
  );
}
