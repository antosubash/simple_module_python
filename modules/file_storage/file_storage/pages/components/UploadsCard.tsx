import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Progress } from '@simple-module-py/ui/components/ui/progress';
import { X } from 'lucide-react';

import type { UploadJob } from '../upload-queue';

interface Props {
  jobs: UploadJob[];
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
  onDismiss: (id: string) => void;
}

/**
 * In-flight and failed uploads, in their own card above the table.
 *
 * They used to be rows inside the table, which meant filtering or paging —
 * the two things people do while waiting — swept the progress bars away. Here
 * they survive both, which is what the card's own subtitle promises.
 */
export function UploadsCard({ jobs, onCancel, onRetry, onDismiss }: Props) {
  const { t } = useT();
  if (jobs.length === 0) return null;

  return (
    <Card className="mb-4 gap-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-bold font-[var(--font-display)]">
          {t(keys.file_storage.upload.card_title)}
        </span>
        <span className="text-xs text-muted-foreground">
          {t(keys.file_storage.upload.card_subtitle)}
        </span>
      </div>
      {jobs.map((job) => (
        <div key={job.id} className="flex items-center gap-3 text-sm">
          <span className="w-40 shrink-0 truncate sm:w-[190px]">{job.name}</span>
          {job.status === 'error' ? (
            <>
              <span className="min-w-0 flex-1 truncate text-destructive">
                {job.reason
                  ? t(keys.file_storage.upload.failed_reason, { reason: job.reason })
                  : t(keys.file_storage.toasts.upload_failed)}
              </span>
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-primary-700"
                onClick={() => onRetry(job.id)}
              >
                {t(keys.file_storage.upload.retry)}
              </Button>
              <DismissButton
                label={t(keys.file_storage.upload.dismiss)}
                onClick={() => onDismiss(job.id)}
              />
            </>
          ) : (
            <>
              <Progress
                value={job.percent}
                className="h-1.5 flex-1"
                aria-label={t(keys.file_storage.upload.in_progress, { name: job.name })}
              />
              <span className="w-11 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
                {job.percent}%
              </span>
              <DismissButton
                label={t(keys.file_storage.upload.cancel)}
                onClick={() => onCancel(job.id)}
              />
            </>
          )}
        </div>
      ))}
    </Card>
  );
}

function DismissButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      className="shrink-0 max-lg:min-h-11 max-lg:min-w-11"
      onClick={onClick}
      aria-label={label}
    >
      <X />
    </Button>
  );
}
