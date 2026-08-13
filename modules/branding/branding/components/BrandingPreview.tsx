import { keys, useT } from '@simple-module-py/i18n';
import { Card, CardContent, CardHeader, CardTitle } from '@simple-module-py/ui/components/ui/card';
import type { MenuItem } from '@simple-module-py/ui/types';

export type PreviewSeverity = 'info' | 'warning' | 'danger';

interface Props {
  appName: string;
  /** Hex colour from the form, or '' to fall back to the default swatch. */
  color: string;
  defaultColor: string;
  logoUrl: string | null;
  /** Dark-surface logo variant; falls back to `logoUrl` like the real sidebar. */
  logoDarkUrl: string | null;
  bannerMessage: string;
  bannerSeverity: PreviewSeverity;
  /** The viewer's own sidebar entries, so the preview shows a real nav. */
  menuItems: MenuItem[];
}

/**
 * Mirrors BrandingBanner's severity map. Duplicated rather than imported
 * because that component reads the *saved* banner from shared props — the
 * whole point here is to render the unsaved form state.
 */
const SEVERITY_CLASS: Record<PreviewSeverity, string> = {
  info: 'bg-sky-600 text-white',
  warning: 'bg-amber-500 text-black',
  danger: 'bg-red-600 text-white',
};

const MAX_NAV_ROWS = 5;

/**
 * Live preview of the sidebar and banner as the form is edited.
 *
 * Previously the preview was a logo tile and the app name, so the two places
 * branding is actually most visible — the sidebar every authenticated page
 * carries, and the site-wide banner — could only be checked by saving and
 * waiting for a full reload. Everything here is driven by form state, so it
 * updates as you type and never needs a round trip.
 */
export function BrandingPreview({
  appName,
  color,
  defaultColor,
  logoUrl,
  logoDarkUrl,
  bannerMessage,
  bannerSeverity,
  menuItems,
}: Props) {
  const { t } = useT();
  const accent = color || defaultColor;
  const name = appName || 'SimpleModule';
  const initial = name.trim()[0]?.toUpperCase() ?? 'S';
  // Same fallback the real sidebar uses: no dark variant means the primary
  // logo has to hold up against the near-black surface.
  const darkLogo = logoDarkUrl ?? logoUrl;
  const rows = menuItems.slice(0, MAX_NAV_ROWS);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t(keys.branding.manage.preview_title)}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-hidden rounded-lg border">
          {bannerMessage ? (
            <div
              className={`px-3 py-1.5 text-center text-xs font-medium ${SEVERITY_CLASS[bannerSeverity]}`}
            >
              {bannerMessage}
            </div>
          ) : (
            <div className="border-b bg-muted/40 px-3 py-1.5 text-center text-[11px] text-muted-foreground">
              {t(keys.branding.manage.preview_no_banner)}
            </div>
          )}

          <div className="flex min-h-[190px]">
            {/* Sidebar. `bg-app-sidebar` is the same near-black token the real
                shell uses, so the dark-variant logo is judged against the
                surface it will actually sit on. */}
            <div className="flex w-32 shrink-0 flex-col bg-app-sidebar">
              {/* Rendered inline rather than via BrandingMark: that component
                  takes its badge colour as a Tailwind class, and the point
                  here is to show the hex currently in the colour field. */}
              <div className="flex h-11 items-center gap-2 border-b border-white/[0.06] px-2.5">
                {darkLogo ? (
                  <img
                    src={darkLogo}
                    alt={name}
                    className="h-6 w-6 shrink-0 rounded-md bg-white/5 object-contain"
                  />
                ) : (
                  <span
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[11px] font-bold text-white"
                    style={{ backgroundColor: accent }}
                  >
                    {initial}
                  </span>
                )}
                <span className="truncate text-[11px] font-semibold text-white">{name}</span>
              </div>
              <div className="space-y-1 px-2 py-2">
                {rows.map((item) => (
                  <div
                    key={item.url}
                    className="truncate rounded px-1.5 py-1 text-[10px] text-white/60"
                  >
                    {item.label}
                  </div>
                ))}
                {rows.length === 0 && (
                  <div className="rounded px-1.5 py-1 text-[10px] text-white/40">—</div>
                )}
              </div>
            </div>

            <div className="flex-1 bg-background p-3">
              <div className="h-2.5 w-20 rounded" style={{ backgroundColor: accent }} />
              <div className="mt-2 h-1.5 w-28 rounded bg-muted" />
              <div className="mt-1.5 h-1.5 w-20 rounded bg-muted" />
              <div
                className="mt-3 inline-flex h-5 items-center rounded px-2 text-[10px] font-medium text-white"
                style={{ backgroundColor: accent }}
              >
                {t(keys.branding.manage.preview_button)}
              </div>
            </div>
          </div>
        </div>

        {/* The original logo-tile preview: the light-surface logo, which the
            sidebar above cannot show because it renders the dark variant. */}
        <div className="flex items-center gap-3 rounded-lg border p-3">
          <div
            className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-lg text-white"
            style={{ backgroundColor: accent }}
          >
            {logoUrl ? (
              <img src={logoUrl} alt={name} className="h-full w-full object-contain" />
            ) : (
              <span className="text-sm font-bold">{name.trim()[0]?.toUpperCase() ?? 'S'}</span>
            )}
          </div>
          <span className="text-sm font-semibold">{name}</span>
        </div>
      </CardContent>
    </Card>
  );
}
