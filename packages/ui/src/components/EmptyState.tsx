import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from '@simple-module-py/ui/components/ui/empty';
import { cn } from '@simple-module-py/ui/lib/utils';
import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  /** Call to action — the one thing to do from here. Omitted when there isn't one. */
  action?: React.ReactNode;
  className?: string;
}

/**
 * The "nothing here" panel every list screen needs.
 *
 * Wraps the `ui/empty` primitives so the four admin lists (users, files, tasks,
 * audit log) read as one treatment rather than four hand-rolled ones. Callers
 * pick the copy, which is the part that must differ: a list emptied by a filter
 * and a list that has genuinely never had rows want opposite messages, and
 * telling someone "nothing uploaded yet" when the bucket is full and their
 * filter is merely too narrow sends them looking for a bug that isn't there.
 */
export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <Empty className={cn('gap-4', className)}>
      <EmptyMedia variant="icon">
        <Icon className="size-5 text-primary-300" aria-hidden="true" />
      </EmptyMedia>
      <EmptyTitle>{title}</EmptyTitle>
      {description && <EmptyDescription>{description}</EmptyDescription>}
      {action && <EmptyContent>{action}</EmptyContent>}
    </Empty>
  );
}
