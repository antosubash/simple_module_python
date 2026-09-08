import type React from 'react';
import { cn } from '../lib/utils';
import { type PageMobileAction, useReportPageHeading } from './page-heading';

interface PageShellProps {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
  actions?: React.ReactNode;
  /** Restrict the inner content to a comfortable reading width. */
  maxWidth?: 'full' | 'screen-xl';
  /**
   * Url of the sidebar section this page belongs to. Only needed when the
   * page's own path sits outside it — otherwise the section is matched from
   * the url and this is redundant.
   */
  section?: string;
  /** Merged over the default heading classes — `font-mono` for task names, ids. */
  titleClassName?: string;
  /** Rendered before the title: an avatar, a status dot, an icon tile. */
  leading?: React.ReactNode;
  /** Rendered beside the title: a status pill. */
  badge?: React.ReactNode;
  /**
   * Compact stand-in for `actions` on phones, shown in the shell's top bar
   * where the deck puts it. The full control stays in `actions` for desktop.
   */
  mobileAction?: PageMobileAction;
  /** Href for the phone bar's back chevron. Detail pages declare their index. */
  back?: string;
  /** Render the phone bar's title in the mono face. */
  mono?: boolean;
  /**
   * Make the shell reach the bottom of the viewport on `lg`, with the content
   * column growing into whatever the heading leaves. A page whose main surface
   * should fill the window then says `lg:flex-1` on that surface instead of
   * subtracting a hand-measured header height from `100vh` — a magic number
   * that silently drifts the moment a heading, tab row or filter bar changes.
   */
  fill?: boolean;
}

export function PageShell({
  title,
  description,
  children,
  actions,
  maxWidth = 'screen-xl',
  section,
  titleClassName,
  leading,
  badge,
  mobileAction,
  back,
  mono,
  fill = false,
}: PageShellProps) {
  // The shell's breadcrumb and phone bar are named from this, so they can never
  // disagree with the heading rendered below.
  useReportPageHeading({ title, section, back, mono, mobileAction });
  const widthClass = maxWidth === 'full' ? '' : 'max-w-screen-xl mx-auto';
  return (
    <div
      className={cn(
        'px-4 py-6 sm:px-6 sm:py-7 lg:px-8',
        widthClass,
        // `min-h` rather than `h`: a page taller than the window still grows,
        // and `--app-chrome-h` is the one variable both bars size themselves
        // off, so this cannot disagree with the topbar.
        fill && 'lg:flex lg:min-h-[calc(100vh-var(--app-chrome-h))] lg:flex-col',
      )}
    >
      <div className="mb-5 flex flex-col gap-3 sm:mb-6 sm:flex-row sm:items-baseline sm:justify-between">
        {/* Phones wrap the title, so a centred avatar drifts off the first
            line; top-align there and centre once the row fits. */}
        <div className="flex min-w-0 items-start gap-3 sm:items-center">
          {leading}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1
                className={cn(
                  'text-[27px] font-bold tracking-[-0.02em] font-display',
                  titleClassName,
                )}
              >
                {title}
              </h1>
              {badge}
            </div>
            {description && (
              <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">{description}</p>
            )}
          </div>
        </div>
        {actions && (
          // A page that also declares `mobileAction` already shows its primary
          // control in the phone bar; repeating it here is a duplicate button.
          <div
            className={cn(
              'flex flex-shrink-0 items-center gap-2',
              mobileAction && 'hidden sm:flex',
            )}
          >
            {actions}
          </div>
        )}
      </div>
      <div className={cn(fill && 'lg:flex lg:min-h-0 lg:flex-1 lg:flex-col')}>{children}</div>
    </div>
  );
}
