import { router } from '@inertiajs/react';
import { useCallback, useState } from 'react';

import { ROUTES } from './constants';

export interface UploadJob {
  id: string;
  name: string;
  size: number;
  /** 0–100. Stays at 100 while the server finishes writing to the backend. */
  percent: number;
  status: 'uploading' | 'done' | 'error';
}

let counter = 0;
function nextId(): string {
  counter += 1;
  return `upload-${counter}`;
}

// Files in a batch have no ordering dependency on one another, so uploading
// strictly one at a time makes a 10-file drop take the sum of every file's
// duration. A small worker pool instead bounds the batch to roughly the
// slowest file's duration without opening enough simultaneous connections to
// swamp the server or the browser's per-origin connection limit.
const UPLOAD_CONCURRENCY = 4;

/**
 * Uploads files with bounded concurrency, reporting byte progress per file.
 *
 * Uses XMLHttpRequest rather than fetch deliberately: fetch exposes no upload
 * progress events in any current browser, and a large file uploading behind a
 * spinner with no feedback is the exact complaint this replaces.
 */
export function useUploadQueue() {
  const [jobs, setJobs] = useState<UploadJob[]>([]);

  const patch = useCallback((id: string, changes: Partial<UploadJob>) => {
    setJobs((current) => current.map((j) => (j.id === id ? { ...j, ...changes } : j)));
  }, []);

  const upload = useCallback(
    (job: UploadJob, file: File) =>
      new Promise<boolean>((resolve) => {
        const form = new FormData();
        form.append('file', file);

        const xhr = new XMLHttpRequest();
        xhr.open('POST', ROUTES.API_UPLOAD);
        xhr.upload.addEventListener('progress', (event) => {
          if (!event.lengthComputable) return;
          patch(job.id, { percent: Math.round((event.loaded / event.total) * 100) });
        });
        xhr.addEventListener('load', () => {
          const ok = xhr.status >= 200 && xhr.status < 300;
          patch(job.id, { percent: 100, status: ok ? 'done' : 'error' });
          resolve(ok);
        });
        // A dropped connection and a rejected upload look the same to the
        // user, so both land on the same visible error row.
        xhr.addEventListener('error', () => {
          patch(job.id, { status: 'error' });
          resolve(false);
        });
        xhr.addEventListener('abort', () => {
          patch(job.id, { status: 'error' });
          resolve(false);
        });
        xhr.send(form);
      }),
    [patch],
  );

  const start = useCallback(
    async (files: FileList | File[]): Promise<{ uploaded: number; failed: string[] }> => {
      const list = Array.from(files);
      if (list.length === 0) return { uploaded: 0, failed: [] };

      const queued: UploadJob[] = list.map((file) => ({
        id: nextId(),
        name: file.name,
        size: file.size,
        percent: 0,
        status: 'uploading',
      }));
      setJobs((current) => [...current, ...queued]);

      let uploaded = 0;
      const failed: string[] = [];
      let next = 0;
      const worker = async () => {
        while (next < list.length) {
          const index = next;
          next += 1;
          const ok = await upload(queued[index], list[index]);
          if (ok) uploaded += 1;
          else failed.push(list[index].name);
        }
      };
      await Promise.all(Array.from({ length: Math.min(UPLOAD_CONCURRENCY, list.length) }, worker));

      // Completed rows disappear once the reloaded table can *show* the real
      // record — dropping them before the reply lands leaves a gap where the
      // table still holds the pre-upload list, and a first upload into an
      // empty bucket flashes "No files yet". Failures stay until dismissed so
      // they can't go unnoticed, and anything still uploading stays too — a
      // second batch dropped while this reload is in flight must not have its
      // progress rows swept away by the first batch's cleanup.
      const clearFinished = () =>
        setJobs((current) =>
          current.filter((j) => j.status === 'error' || j.status === 'uploading'),
        );
      if (uploaded > 0) {
        router.reload({
          only: ['files', 'pagination', 'content_types'],
          onFinish: clearFinished,
        });
      } else {
        clearFinished();
      }
      return { uploaded, failed };
    },
    [upload],
  );

  const dismiss = useCallback((id: string) => {
    setJobs((current) => current.filter((j) => j.id !== id));
  }, []);

  // Derived, not tracked separately: a ref would not re-render the button and
  // a second state field could disagree with the rows on screen.
  const busy = jobs.some((j) => j.status === 'uploading');

  return { jobs, start, dismiss, busy };
}
