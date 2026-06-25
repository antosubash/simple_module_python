import type React from 'react';

interface BrandingMarkProps {
  /** Application name — shown as the wordmark and used for the fallback initial. */
  appName: string;
  /** Custom logo URL. When absent, a generated initial badge is shown. */
  logoUrl?: string | null;
  /** Tailwind classes for the fallback badge background (e.g. a gradient). */
  accentColor: string;
  /** Visual size — `sm` for the mobile bar, `md` for the desktop sidebar. */
  size?: 'sm' | 'md';
  /** Classes for the wordmark text (colour/spacing supplied by the layout). */
  labelClassName?: string;
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
  caption,
  captionClassName,
}: BrandingMarkProps): React.ReactElement {
  const box = size === 'sm' ? 'w-7 h-7 rounded-md' : 'w-8 h-8 rounded-lg';
  const labelSize = size === 'sm' ? 'text-base' : 'text-lg';
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
        <img src={logoUrl} alt={appName} className={`${box} object-contain bg-white/5 shadow-sm`} />
      ) : (
        <div className={`${box} ${accentColor} flex items-center justify-center shadow-sm`}>
          <span className="text-white font-bold text-xs font-[var(--font-display)]">{initial}</span>
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
