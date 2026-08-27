import { BRAND_ACCENT, BRAND_FOOTER_LINKS, BRAND_LICENSE, type BrandLink } from '../lib/brand';
import { BrandingMark } from './BrandingMark';

/** Stable for the lifetime of the bundle — the year only matters at page load. */
const FOOTER_YEAR = new Date().getFullYear();

interface BrandingFooterProps {
  /** Application name from the `branding` shared prop. */
  appName: string;
  /** Custom logo URL; falls back to the generated initial badge. */
  logoUrl?: string | null;
  /**
   * `public` centres the row within `max-w-6xl` (marketing pages); `app` spans
   * the full content width of the sidebar shell.
   */
  variant?: 'app' | 'public';
  /**
   * Links shown on the right. Omitted or `null` falls back to the framework's
   * own `BRAND_FOOTER_LINKS`, so a host that configures nothing is unchanged.
   * Layouts pass the `branding` shared prop's `footerLinks` through, which is
   * what makes the footer white-labellable without forking this component.
   */
  links?: BrandLink[] | null;
}

/** Framework-owned footer shared by the authenticated and public layouts. */
export function BrandingFooter({
  appName,
  logoUrl,
  variant = 'app',
  links,
}: BrandingFooterProps): React.ReactElement {
  // An empty array is treated as "unset" too: it is what the server sends
  // for a deployment that has cleared its links, and a footer with no links
  // at all reads as broken rather than deliberate.
  const shown = links?.length ? links : BRAND_FOOTER_LINKS;
  const container =
    variant === 'public' ? 'mx-auto max-w-6xl px-4 py-6 sm:px-8' : 'px-4 py-6 sm:px-6 lg:px-8';

  return (
    <footer className="mt-auto border-t border-border bg-background">
      <div className={`flex flex-wrap items-center justify-between gap-4 ${container}`}>
        <div className="flex items-center gap-2.5">
          <BrandingMark
            appName={appName}
            logoUrl={logoUrl}
            accentColor={BRAND_ACCENT}
            size="sm"
            labelClassName="text-sm font-semibold tracking-tight text-foreground font-[var(--font-display)]"
            caption={`© ${FOOTER_YEAR} · ${BRAND_LICENSE}`}
          />
        </div>
        <nav className="flex flex-wrap items-center gap-5 text-xs text-muted-foreground">
          {shown.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="transition-colors hover:text-foreground"
              rel="noopener noreferrer"
            >
              {link.label}
            </a>
          ))}
        </nav>
      </div>
    </footer>
  );
}
