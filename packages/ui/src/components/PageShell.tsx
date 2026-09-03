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
}: PageShellProps) {
  // The shell's breadcrumb and phone bar are named from this, so they can never
  // disagree with the heading rendered below.
  useReportPageHeading({ title, section, back, mono, mobileAction });
  const widthClass = maxWidth === 'full' ? '' : 'max-w-screen-xl mx-auto';
  return (
    <div className={`px-4 py-6 sm:px-6 sm:py-7 lg:px-8 ${widthClass}`}>
      <div className="mb-5 flex flex-col gap-3 sm:mb-6 sm:flex-row sm:items-baseline sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          {leading}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1
                className={cn(
                  'text-2xl font-bold tracking-tight font-[var(--font-display)]',
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
        {actions && <div className="flex flex-shrink-0 items-center gap-2">{actions}</div>}
      </div>
      <div>{children}</div>
    </div>
  );
}
