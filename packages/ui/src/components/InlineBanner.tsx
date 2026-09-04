import { Card } from '@simple-module-py/ui/components/ui/card';
import { cn } from '@simple-module-py/ui/lib/utils';
import type { LucideIcon } from 'lucide-react';
import type React from 'react';

interface InlineBannerProps {
  icon: LucideIcon;
  /** `info` for a neutral status note, `warning` for something that needs attention. */
  tone?: 'info' | 'warning';
  title: React.ReactNode;
  /** Omit for a one-line banner — the deck's mailer strip is a single sentence. */
  description?: React.ReactNode;
  /** Usually a button/link — the one thing to do about this banner. */
  action?: React.ReactNode;
  /** Vertical alignment of the icon/text block against the trailing action. */
  align?: 'center' | 'start';
  className?: string;
}

const TONE_CARD: Record<NonNullable<InlineBannerProps['tone']>, string> = {
  info: 'border-primary/30 bg-primary/5',
  warning: 'border-amber-300 bg-amber-50 dark:bg-amber-950/30',
};

const TONE_ICON: Record<NonNullable<InlineBannerProps['tone']>, string> = {
  info: 'text-primary-600',
  warning: 'text-amber-600',
};

const TONE_TITLE: Record<NonNullable<InlineBannerProps['tone']>, string> = {
  info: 'text-sm font-medium',
  warning: 'text-sm font-medium text-amber-900 dark:text-amber-200',
};

const TONE_DESCRIPTION: Record<NonNullable<InlineBannerProps['tone']>, string> = {
  info: 'text-xs text-muted-foreground',
  warning: 'text-xs text-amber-800/80 dark:text-amber-200/70',
};

/**
 * A card-style informational strip: icon, title/description, trailing action.
 *
 * `CorrelationBanner` (audit_log) and `WorkerHealthBanner` (background_tasks)
 * each hand-rolled this exact shape — same `Card`, same icon+text+action
 * layout, differing only in color and copy. Consolidated here so a third
 * module doesn't reinvent it a third time, the way `EmptyState` already
 * consolidated the "nothing here" panel.
 */
export function InlineBanner({
  icon: Icon,
  tone = 'info',
  title,
  description,
  action,
  align = 'center',
  className,
}: InlineBannerProps) {
  return (
    <Card
      className={cn(
        'mb-4 flex flex-row justify-between gap-3 px-4 py-3',
        align === 'center' ? 'items-center' : 'items-start',
        TONE_CARD[tone],
        className,
      )}
    >
      <div className="flex items-start gap-2.5">
        <Icon className={cn('mt-0.5 size-4 shrink-0', TONE_ICON[tone])} aria-hidden="true" />
        <div>
          <p className={TONE_TITLE[tone]}>{title}</p>
          {description && <p className={TONE_DESCRIPTION[tone]}>{description}</p>}
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </Card>
  );
}
