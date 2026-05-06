import { cn } from '@simple-module-py/ui/lib/utils';
import type React from 'react';

interface SectionTitleProps {
  children: React.ReactNode;
  description?: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
  as?: 'h2' | 'h3';
}

export function SectionTitle({
  children,
  description,
  right,
  className,
  as = 'h3',
}: SectionTitleProps) {
  const Tag = as;
  const size = as === 'h2' ? 'text-lg' : 'text-base';
  return (
    <div className={cn('mb-3', className)}>
      <div className="flex items-center justify-between gap-3">
        <Tag
          className={cn(
            'flex items-center gap-2.5 font-bold tracking-tight font-[var(--font-display)] text-foreground',
            size,
          )}
        >
          <span className="block h-[18px] w-1 rounded-full bg-gradient-to-b from-primary-600 to-primary-800" />
          {children}
        </Tag>
        {right}
      </div>
      {description && <p className="mt-1 ml-3.5 text-sm text-muted-foreground">{description}</p>}
    </div>
  );
}
