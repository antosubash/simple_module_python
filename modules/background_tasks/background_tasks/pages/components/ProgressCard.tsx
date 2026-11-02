import { keys, useT } from '@simple-module-py/i18n';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Progress } from '@simple-module-py/ui/components/ui/progress';
import type { TaskDetail } from '../constants';

interface Props {
  execution: Pick<
    TaskDetail,
    'progress_current' | 'progress_total' | 'progress_message' | 'progress_phase'
  >;
  className?: string;
}

/** The task's own progress report, when it sent one. */
export function ProgressCard({ execution, className }: Props) {
  const { t } = useT();
  const { progress_current: current, progress_total: total } = execution;
  if (current == null || total == null) return null;

  const percent = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
  return (
    <Card className={className} data-testid="task-progress">
      <div className="flex items-baseline justify-between gap-3 px-4 text-sm">
        <span className="font-medium">
          {execution.progress_phase ?? t(keys.background_tasks.detail.progress)}
        </span>
        <span className="font-mono text-muted-foreground">
          {t(keys.background_tasks.detail.progress_count, { current, total, percent })}
        </span>
      </div>
      <div className="px-4">
        <Progress
          value={percent}
          aria-label={t(keys.background_tasks.detail.progress)}
          aria-valuenow={percent}
        />
      </div>
      {execution.progress_message && (
        <p className="px-4 text-sm text-muted-foreground">{execution.progress_message}</p>
      )}
    </Card>
  );
}
