import { BRAND_ACCENT, BRAND_FOOTER_LINKS, BRAND_LICENSE } from '../lib/brand';
import type { FooterShared } from '../types';
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
   * Admin-configured footer. When absent the framework footer below is used
   * unchanged, so a deployment that never configures one is unaffected.
   */
  footer?: FooterShared | null;
}

function FooterLinkAnchor({ label, href }: { label: string; href: string }) {
  // Server-side `validate_href` restricts these to http(s) and in-app paths.
  // `noopener` still matters: an external target must not get window.opener.
  const external = !href.startsWith('/');
  return (
    <a
      href={href}
      className="transition-colors hover:text-foreground"
      {...(external ? { rel: 'noopener noreferrer' } : {})}
    >
      {label}
    </a>
  );
}

/**
 * App-wide footer: brand lockup on the left, links on the right.
 *
 * Renders one of two shapes. With no configured footer it keeps the framework's
 * single row of project links. Once an admin configures columns or social
 * links it becomes a multi-column footer with the brand block above a bottom
 * bar. Presentational (props-driven) so it renders without Inertia context and
 * is shared by both the authenticated shell and the public layout.
 */
export function BrandingFooter({
  appName,
  logoUrl,
  variant = 'app',
  footer = null,
}: BrandingFooterProps): React.ReactElement {
  const container =
    variant === 'public' ? 'mx-auto max-w-6xl px-4 py-6 sm:px-8' : 'px-4 py-6 sm:px-6 lg:px-8';
  const configured = footer && (footer.columns.length > 0 || footer.socialLinks.length > 0);
  const caption = footer?.note || `© ${FOOTER_YEAR} · ${BRAND_LICENSE}`;
  const mark = (
    <BrandingMark
      appName={appName}
      logoUrl={logoUrl}
      accentColor={BRAND_ACCENT}
      size="sm"
      labelClassName="text-sm font-semibold tracking-tight text-foreground font-[var(--font-display)]"
      caption={caption}
    />
  );

  if (!configured) {
    return (
      <footer className="mt-auto border-t border-border bg-background">
        <div className={`flex flex-wrap items-center justify-between gap-4 ${container}`}>
          <div className="flex items-center gap-2.5">{mark}</div>
          <nav className="flex flex-wrap items-center gap-5 text-xs text-muted-foreground">
            {BRAND_FOOTER_LINKS.map((link) => (
              <FooterLinkAnchor key={link.href} label={link.label} href={link.href} />
            ))}
          </nav>
        </div>
      </footer>
    );
  }

  return (
    <footer className="mt-auto border-t border-border bg-background">
      <div className={container}>
        <div className="flex flex-wrap justify-between gap-8">
          <div className="max-w-xs">
            <div className="flex items-center gap-2.5">{mark}</div>
            {footer?.tagline && (
              <p className="mt-3 text-xs text-muted-foreground">{footer.tagline}</p>
            )}
          </div>
          <div className="flex flex-wrap gap-8">
            {footer?.columns.map((column) => (
              <nav key={column.title} className="min-w-32">
                <h2 className="mb-2 text-xs font-semibold tracking-wide text-foreground uppercase">
                  {column.title}
                </h2>
                <ul className="space-y-1.5 text-xs text-muted-foreground">
                  {column.links.map((link) => (
                    <li key={`${link.label}-${link.href}`}>
                      <FooterLinkAnchor label={link.label} href={link.href} />
                    </li>
                  ))}
                </ul>
              </nav>
            ))}
          </div>
        </div>
        {(footer?.copyrightOwner || (footer?.socialLinks.length ?? 0) > 0) && (
          <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-border pt-4 text-xs text-muted-foreground">
            <span>{footer?.copyrightOwner ? `© ${FOOTER_YEAR} ${footer.copyrightOwner}` : ''}</span>
            <nav className="flex flex-wrap items-center gap-4">
              {footer?.socialLinks.map((link) => (
                <FooterLinkAnchor key={link.href} label={link.label} href={link.href} />
              ))}
            </nav>
          </div>
        )}
      </div>
    </footer>
  );
}
