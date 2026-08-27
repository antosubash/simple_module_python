import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Progress } from '@simple-module-py/ui/components/ui/progress';
import { TableCell, TableRow } from '@simple-module-py/ui/components/ui/table';
import { AlertCircle, X } from 'lucide-react';

import type { UploadJob } from '../upload-queue';

interface Props {
  jobs: UploadJob[];
  onDismiss: (id: string) => void;
  columnCount: number;
}

/** In-flight and failed uploads, shown as rows above the stored files. */
export function UploadProgressRows({ jobs, onDismiss, columnCount }: Props) {
  const { t } = useT();
  if (jobs.length === 0) return null;

  return (
    <>
      {jobs.map((job) => (
        <TableRow key={job.id} className="bg-muted/30">
          <TableCell colSpan={columnCount} className="sm:px-6">
            <div className="flex items-center gap-3">
              {job.status === 'error' ? (
                <AlertCircle className="size-4 shrink-0 text-destructive" aria-hidden="true" />
              ) : null}
              {/* Filenames are arbitrary-length and this row is the only place
                  an in-flight upload is named. */}
              <span title={job.name} className="min-w-0 flex-1 truncate text-sm font-medium">
                {job.name}
              </span>
              {job.status === 'error' ? (
                <>
                  <span className="text-xs text-destructive">
                    {t(keys.file_storage.toasts.upload_failed)}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => onDismiss(job.id)}
                    aria-label={t(keys.file_storage.upload.dismiss)}
                  >
                    <X />
                  </Button>
                </>
              ) : (
                <>
                  <Progress
                    value={job.percent}
                    className="h-1.5 w-40"
                    aria-label={t(keys.file_storage.upload.in_progress, { name: job.name })}
                  />
                  <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">
                    {job.percent}%
                  </span>
                </>
              )}
            </div>
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}
