import type React from 'react';
import { useReportPageHeading } from './page-heading';

interface PageShellProps {
  title: string;
  description?: string;
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
}

export function PageShell({
  title,
  description,
  children,
  actions,
  maxWidth = 'screen-xl',
  section,
}: PageShellProps) {
  // The shell's breadcrumb names the page from this, so it can never disagree
  // with the heading rendered below.
  useReportPageHeading(title, section);
  const widthClass = maxWidth === 'full' ? '' : 'max-w-screen-xl mx-auto';
  return (
    <div className={`px-4 py-6 sm:px-6 sm:py-7 lg:px-8 ${widthClass}`}>
      <div className="mb-5 flex flex-col gap-3 sm:mb-6 sm:flex-row sm:items-baseline sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight font-[var(--font-display)]">{title}</h1>
          {description && (
            <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">{description}</p>
          )}
        </div>
        {actions && <div className="flex flex-shrink-0 items-center gap-2">{actions}</div>}
      </div>
      <div>{children}</div>
    </div>
  );
}
