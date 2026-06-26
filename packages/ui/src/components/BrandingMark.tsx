import type React from 'react';

interface BrandingMarkProps {
  /** Application name — shown as the wordmark and used for the fallback initial. */
  appName: string;
  /** Custom logo URL. When absent, a generated initial badge is shown. */
  logoUrl?: string | null;
  /** Tailwind classes for the fallback badge background (e.g. a gradient). */
  accentColor: string;
  /** Visual size — `sm` mobile bar, `md` desktop sidebar, `lg` auth screens. */
  size?: 'sm' | 'md' | 'lg';
  /** Classes for the wordmark text (colour/spacing supplied by the layout). */
  labelClassName?: string;
  /** Override for the badge shadow (defaults to `shadow-sm`; e.g. a coloured glow). */
  badgeClassName?: string;
  /** Optional muted sub-caption stacked under the wordmark (e.g. `python`, `© 2026 · MIT`). */
  caption?: string;
  /** Classes for the caption text. Defaults to a muted mono line. */
  captionClassName?: string;
}

/**
 * App logo + wordmark. Renders the uploaded logo when set, otherwise a badge
 * with the app's initial. Pure/presentational so it can be unit-tested without
 * Inertia context.
 */
export function BrandingMark({
  appName,
  logoUrl,
  accentColor,
  size = 'md',
  labelClassName,
  badgeClassName,
  caption,
  captionClassName,
}: BrandingMarkProps): React.ReactElement {
  const box =
    size === 'sm'
      ? 'w-7 h-7 rounded-md'
      : size === 'lg'
        ? 'w-9 h-9 rounded-lg'
        : 'w-8 h-8 rounded-lg';
  const labelSize = size === 'sm' ? 'text-base' : 'text-lg';
  const initialSize = size === 'lg' ? 'text-base' : 'text-xs';
  const badgeShadow = badgeClassName ?? 'shadow-sm';
  const initial = appName.trim().charAt(0).toUpperCase() || 'S';

  const wordmark = (
    <span
      className={
        labelClassName ??
        `${labelSize} font-semibold text-white font-[var(--font-display)] tracking-tight`
      }
    >
      {appName}
    </span>
  );

  return (
    <>
      {logoUrl ? (
        <img
          src={logoUrl}
          alt={appName}
          className={`${box} object-contain bg-white/5 ${badgeShadow}`}
        />
      ) : (
        <div className={`${box} ${accentColor} flex items-center justify-center ${badgeShadow}`}>
          <span className={`text-white font-bold ${initialSize} font-[var(--font-display)]`}>
            {initial}
          </span>
        </div>
      )}
      {caption ? (
        <span className="flex flex-col leading-tight">
          {wordmark}
          <span className={captionClassName ?? 'font-mono text-[11px] text-muted-foreground'}>
            {caption}
          </span>
        </span>
      ) : (
        wordmark
      )}
    </>
  );
}
