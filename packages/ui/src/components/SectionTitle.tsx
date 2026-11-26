import { cn } from '@simple-module-py/ui/lib/utils';
import type React from 'react';

interface SectionTitleProps extends Pick<React.ComponentPropsWithRef<'h3'>, 'ref' | 'tabIndex'> {
  children: React.ReactNode;
  description?: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
  as?: 'h2' | 'h3';
}

/**
 * A section heading with optional description and trailing controls.
 * `ref` and `tabIndex` target the heading, not its wrapper; use `tabIndex={-1}`
 * to restore focus programmatically without adding a tab stop.
 */
export function SectionTitle({
  children,
  description,
  right,
  className,
  as = 'h3',
  ref,
  tabIndex,
}: SectionTitleProps) {
  const Tag = as;
  const size = as === 'h2' ? 'text-lg' : 'text-base';
  return (
    <div className={cn('mb-3', className)}>
      <div className="flex items-center justify-between gap-3">
        <Tag
          ref={ref}
          tabIndex={tabIndex}
          className={cn(
            'flex items-center gap-2.5 font-bold tracking-tight font-display text-foreground',
            size,
          )}
        >
          {children}
        </Tag>
        {right}
      </div>
      {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
    </div>
  );
}
