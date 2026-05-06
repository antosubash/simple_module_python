import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { cn } from '@simple-module-py/ui/lib/utils';
import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  delta?: string;
  deltaTone?: 'success' | 'info' | 'warning' | 'destructive' | 'secondary';
  className?: string;
}

export function StatCard({
  label,
  value,
  icon: Icon,
  delta,
  deltaTone = 'success',
  className,
}: StatCardProps) {
  const deltaVariant: Record<NonNullable<StatCardProps['deltaTone']>, string> = {
    success: 'border-primary-200 bg-primary-50 text-primary-700',
    info: 'border-blue-200 bg-blue-50 text-blue-700',
    warning: 'border-amber-200 bg-amber-50 text-amber-700',
    destructive: 'border-red-200 bg-red-50 text-red-700',
    secondary: 'border-border bg-secondary text-muted-foreground',
  };
  return (
    <Card className={cn('border-border', className)}>
      <CardContent className="pt-5">
        <div className="flex items-start justify-between">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-primary-600/10 text-primary-700">
            <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
          </span>
          {delta && (
            <Badge variant="outline" className={cn('font-semibold', deltaVariant[deltaTone])}>
              {delta}
            </Badge>
          )}
        </div>
        <div className="mt-3 font-bold tracking-tight font-[var(--font-display)] text-[26px] text-foreground">
          {value}
        </div>
        <div className="mt-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          {label}
        </div>
      </CardContent>
    </Card>
  );
}
