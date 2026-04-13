import type React from 'react';

const CONTENT_DELAY = { animationDelay: '100ms' } as const;

interface PageShellProps {
  title: string;
  description?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}

export function PageShell({ title, description, children, actions }: PageShellProps) {
  return (
    <div className="px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <div className="flex flex-col gap-4 mb-6 sm:flex-row sm:items-center sm:justify-between sm:mb-8 animate-fade-in-up">
        <div>
          <h1 className="text-xl font-bold tracking-tight sm:text-2xl font-[var(--font-display)]">
            {title}
          </h1>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex items-center gap-3">{actions}</div>}
      </div>
      <div className="animate-fade-in-up" style={CONTENT_DELAY}>
        {children}
      </div>
    </div>
  );
}
