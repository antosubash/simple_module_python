import { BRAND_FOOTER_LINKS, BRAND_LICENSE } from '@simple-module-py/ui/lib/brand';
import type { FooterLink } from './dirty';

/** Everything the three preview surfaces read, straight from form state. */
export interface PreviewBrand {
  appName: string;
  /** Resolved hex — the form's colour, or the default swatch. */
  accent: string;
  logoUrl: string | null;
  /** Dark-surface variant; falls back to `logoUrl` like the real sidebar. */
  logoDarkUrl: string | null;
  bannerMessage: string;
  /** Caption line; blank falls back to the framework's own. */
  footerText: string;
  footerLinks: FooterLink[];
  /** The viewer's own sidebar entries, so the mini nav shows a real menu. */
  menuLabels: string[];
}

const MAX_NAV_ROWS = 4;
const PREVIEW_YEAR = new Date().getFullYear();

export function previewFooterLinks(brand: PreviewBrand): FooterLink[] {
  // Same rule as BrandingFooter: an empty list falls back to the framework's
  // own links rather than rendering an empty row.
  return brand.footerLinks.length > 0 ? brand.footerLinks : BRAND_FOOTER_LINKS;
}

/**
 * The banner strip, in the brand colour.
 *
 * The real `BrandingBanner` colours by severity, which is right on a live page
 * — an outage notice must not read as decoration. Here the whole point is to
 * show the chosen colour on the largest surface that carries it, so the
 * preview deliberately diverges. It is labelled a preview; nothing is at stake.
 */
function BannerStrip({ brand }: { brand: PreviewBrand }) {
  if (!brand.bannerMessage) return null;
  return (
    <div
      className="truncate px-2.5 py-1.5 text-[11px] text-white"
      style={{ backgroundColor: brand.accent }}
    >
      {brand.bannerMessage}
    </div>
  );
}

function BrandBadge({ brand, size }: { brand: PreviewBrand; size: string }) {
  const logo = brand.logoDarkUrl ?? brand.logoUrl;
  const initial = brand.appName.trim()[0]?.toUpperCase() ?? 'S';
  return logo ? (
    <img src={logo} alt={brand.appName} className={`${size} shrink-0 rounded object-contain`} />
  ) : (
    <span
      aria-hidden="true"
      className={`${size} shrink-0 rounded`}
      style={{ backgroundColor: brand.accent }}
    >
      <span className="sr-only">{initial}</span>
    </span>
  );
}

function FooterStrip({ brand }: { brand: PreviewBrand }) {
  return (
    <div className="flex items-center justify-between gap-2 border-t border-border bg-card px-2.5 py-1 text-[8px] text-muted-foreground">
      <span className="truncate">
        {brand.footerText.trim() || `© ${PREVIEW_YEAR} ${brand.appName} · ${BRAND_LICENSE}`}
      </span>
      <span className="truncate">
        {previewFooterLinks(brand)
          .map((link) => link.label)
          .join(' · ')}
      </span>
    </div>
  );
}

/**
 * The app shell as branding changes it: banner, sidebar, topbar, content,
 * footer. Driven entirely by form state, so it updates as you type and never
 * needs a round trip.
 */
export function BrandingPreview({ brand }: { brand: PreviewBrand }) {
  const rows = brand.menuLabels.slice(0, MAX_NAV_ROWS);

  return (
    <div className="flex min-h-52 flex-1 flex-col overflow-hidden rounded-[10px] border border-border">
      <BannerStrip brand={brand} />
      <div className="flex min-h-0 flex-1">
        <div className="flex w-[74px] shrink-0 flex-col gap-1.5 bg-app-sidebar px-1.5 py-2">
          <div className="flex items-center gap-1.5">
            <BrandBadge brand={brand} size="h-3.5 w-3.5" />
            <span className="truncate text-[8px] font-bold text-white font-[var(--font-display)]">
              {brand.appName}
            </span>
          </div>
          <div className="h-2 rounded-[3px]" style={{ backgroundColor: brand.accent }} />
          {rows.map((label, index) => (
            <div
              // Decorative bars: two menu entries can share a label, and the
              // list is static within a render.
              // biome-ignore lint/suspicious/noArrayIndexKey: see above
              key={`${label}-${index}`}
              className="h-2 rounded-[3px] bg-white/10"
            />
          ))}
        </div>

        <div className="flex min-w-0 flex-1 flex-col bg-background">
          <div className="h-[22px] border-b border-border bg-card" />
          <div className="flex flex-1 flex-col gap-2 p-3">
            <div className="h-2.5 w-[45%] rounded bg-secondary" />
            <div className="grid grid-cols-3 gap-1.5">
              <div className="h-8 rounded-[7px] border border-border bg-card" />
              <div className="h-8 rounded-[7px] border border-border bg-card" />
              <div className="h-8 rounded-[7px] border border-border bg-card" />
            </div>
            <div className="h-6 w-[88px] rounded-[7px]" style={{ backgroundColor: brand.accent }} />
          </div>
          <FooterStrip brand={brand} />
        </div>
      </div>
    </div>
  );
}
