import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { cn } from '@simple-module-py/ui/lib/utils';
import type { LucideIcon } from 'lucide-react';
import type React from 'react';

interface StatCardProps {
  label: string;
  value: React.ReactNode;
  icon?: LucideIcon;
  /** A short qualifier under the value — "+12 this week", "all healthy". */
  delta?: string;
  deltaTone?: 'success' | 'info' | 'warning' | 'destructive' | 'secondary';
  /** Muted text right after the value, e.g. the denominator in "5 / 8". */
  suffix?: string;
  /** Tints the whole card, for a figure that is itself the bad news. */
  tone?: 'default' | 'warning' | 'destructive';
  valueClassName?: string;
  className?: string;
}

const CARD_TONE: Record<NonNullable<StatCardProps['tone']>, string> = {
  default: '',
  // The deck tints label and figure alike: on a tinted tile the label is part
  // of the warning, not neutral chrome sitting on a coloured background.
  warning:
    'bg-amber-600/5 border-amber-200 [&_.stat-value]:text-amber-700 [&_[data-slot=stat-label]]:text-amber-700',
  destructive:
    'bg-red-50/60 border-red-200 [&_.stat-value]:text-red-700 [&_[data-slot=stat-label]]:text-red-700',
};

const DELTA_TONE: Record<NonNullable<StatCardProps['deltaTone']>, string> = {
  success: 'text-primary-700',
  info: 'text-blue-700',
  warning: 'text-amber-700',
  destructive: 'text-red-700',
  secondary: 'text-muted-foreground',
};

/**
 * One number, read at a glance.
 *
 * The label leads and the value follows, because a row of these is scanned by
 * label first — the figure means nothing until you know what it counts. It is
 * set in sentence case, not the uppercase micro-caption this used to be: the
 * label is a short phrase to read, not a section divider. The delta is plain
 * coloured text rather than a badge, because a badge competes with the value
 * for attention and the value is the point.
 */
export function StatCard({
  label,
  value,
  icon: Icon,
  delta,
  deltaTone = 'success',
  suffix,
  tone = 'default',
  valueClassName,
  className,
}: StatCardProps) {
  return (
    <Card className={cn('gap-0 border-border py-[18px]', CARD_TONE[tone], className)}>
      <CardContent className="px-5">
        <div className="flex items-start justify-between gap-2">
          <span data-slot="stat-label" className="text-[13px] font-medium text-muted-foreground">
            {label}
          </span>
          {Icon && (
            // The deck's phone frame drops the icon tile: at 390px the label
            // and figure are the whole tile and the icon only steals width.
            <span className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-600/10 text-primary-700 sm:inline-flex">
              <Icon className="h-4 w-4" aria-hidden="true" />
            </span>
          )}
        </div>
        <div className="mt-2.5 flex items-baseline gap-1.5">
          <span
            className={cn(
              'stat-value font-bold tracking-[-0.02em] font-display text-[30px] text-foreground',
              valueClassName,
            )}
          >
            {value}
          </span>
          {suffix && <span className="text-sm text-muted-foreground">{suffix}</span>}
        </div>
        {delta && (
          <div data-slot="stat-delta" className={cn('mt-0.5 text-sm', DELTA_TONE[deltaTone])}>
            {delta}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
