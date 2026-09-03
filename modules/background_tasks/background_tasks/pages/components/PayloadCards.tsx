import { keys, useT } from '@simple-module-py/i18n';
import { Card } from '@simple-module-py/ui/components/ui/card';
import type { ReactNode } from 'react';
import { formatPayload, type TaskDetail } from '../constants';

interface Props {
  execution: TaskDetail;
  className?: string;
}

function PayloadCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card className="gap-2.5 p-4 lg:p-[18px]">
      <span className="text-sm font-bold font-[var(--font-display)]">{title}</span>
      <code className="overflow-x-auto rounded-lg bg-secondary px-3 py-2.5 font-mono text-xs text-muted-foreground">
        {children}
      </code>
    </Card>
  );
}

/**
 * What the task was called with — and what it returned, when it returned
 * something.
 *
 * Side by side rather than stacked: args and kwargs are two halves of one call
 * signature, and reading them a screen apart is reading them out of context.
 * The Result card only appears for a run that produced one, which is why it
 * sits below rather than as a third column that is usually empty.
 */
export function PayloadCards({ execution, className }: Props) {
  const { t } = useT();
  return (
    <div className={`flex flex-col gap-3.5 ${className ?? ''}`}>
      <div className="grid gap-3.5 sm:grid-cols-2">
        <PayloadCard title={t(keys.background_tasks.detail.args)}>
          {formatPayload(execution.args ?? [])}
        </PayloadCard>
        <PayloadCard title={t(keys.background_tasks.detail.kwargs)}>
          {formatPayload(execution.kwargs ?? {})}
        </PayloadCard>
      </div>
      {execution.result !== null && (
        <PayloadCard title={t(keys.background_tasks.detail.result)}>
          {formatPayload(execution.result)}
        </PayloadCard>
      )}
    </div>
  );
}
