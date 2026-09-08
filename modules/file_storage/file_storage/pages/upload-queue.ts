import { router } from '@inertiajs/react';
import { useCallback, useRef, useState } from 'react';

import { RELOAD_PROPS, ROUTES } from './constants';

export interface UploadJob {
  id: string;
  name: string;
  size: number;
  /** 0–100. Stays at 100 while the server finishes writing to the backend. */
  percent: number;
  status: 'uploading' | 'done' | 'error';
  /** Why it failed, in the server's words. Undefined for a transport failure. */
  reason?: string;
}

type Outcome = 'done' | 'error' | 'canceled';

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
 * The server's own explanation for a rejected upload.
 *
 * "Upload failed" is true of a 413, a 415 and a dropped connection alike, and
 * it tells the person holding a 40 MB file nothing they can act on. The API
 * already answers with `{"detail": {"code", "message"}}`; this reads it back
 * out and tolerates every shape that is not that — a proxy's HTML error page,
 * an empty body, a plain-string `detail`.
 */
export function parseFailureReason(body: string): string | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return undefined;
  }
  const detail = (parsed as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail || undefined;
  const message = (detail as { message?: unknown } | null)?.message;
  return typeof message === 'string' && message ? message : undefined;
}

/**
 * Uploads files with bounded concurrency, reporting byte progress per file.
 *
 * Uses XMLHttpRequest rather than fetch deliberately: fetch exposes no upload
 * progress events in any current browser, and a large file uploading behind a
 * spinner with no feedback is the exact complaint this replaces.
 *
 * The queue keeps the `File` object for every job it has seen, so a failed row
 * can be retried from the row itself — the alternative is asking the person to
 * find the file on disk again to answer a transient 502.
 */
export function useUploadQueue() {
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const files = useRef(new Map<string, File>());
  const requests = useRef(new Map<string, XMLHttpRequest>());

  const patch = useCallback((id: string, changes: Partial<UploadJob>) => {
    setJobs((current) => current.map((j) => (j.id === id ? { ...j, ...changes } : j)));
  }, []);

  const upload = useCallback(
    (jobId: string, file: File) =>
      new Promise<Outcome>((resolve) => {
        const form = new FormData();
        form.append('file', file);

        const xhr = new XMLHttpRequest();
        requests.current.set(jobId, xhr);
        const settle = (outcome: Outcome) => {
          requests.current.delete(jobId);
          resolve(outcome);
        };

        xhr.open('POST', ROUTES.API_UPLOAD);
        xhr.upload.addEventListener('progress', (event) => {
          if (!event.lengthComputable) return;
          patch(jobId, { percent: Math.round((event.loaded / event.total) * 100) });
        });
        xhr.addEventListener('load', () => {
          const ok = xhr.status >= 200 && xhr.status < 300;
          patch(jobId, {
            percent: 100,
            status: ok ? 'done' : 'error',
            reason: ok ? undefined : parseFailureReason(xhr.responseText),
          });
          settle(ok ? 'done' : 'error');
        });
        // A dropped connection and a rejected upload look the same to the
        // user, so both land on the same visible error row.
        xhr.addEventListener('error', () => {
          patch(jobId, { status: 'error' });
          settle('error');
        });
        // Only ever fired by `cancel` below, which has already removed the row.
        xhr.addEventListener('abort', () => settle('canceled'));
        xhr.send(form);
      }),
    [patch],
  );

  // Completed rows disappear once the reloaded table can *show* the real
  // record — dropping them before the reply lands leaves a gap where the
  // table still holds the pre-upload list, and a first upload into an
  // empty bucket flashes "No files yet". Failures stay until dismissed so
  // they can't go unnoticed, and anything still uploading stays too — a
  // second batch dropped while this reload is in flight must not have its
  // progress rows swept away by the first batch's cleanup.
  const settleBatch = useCallback((uploaded: number) => {
    const clearFinished = () => setJobs((current) => current.filter((j) => j.status !== 'done'));
    if (uploaded > 0) {
      router.reload({ only: RELOAD_PROPS, onFinish: clearFinished });
    } else {
      clearFinished();
    }
  }, []);

  const start = useCallback(
    async (incoming: FileList | File[]): Promise<{ uploaded: number; failed: string[] }> => {
      const list = Array.from(incoming);
      if (list.length === 0) return { uploaded: 0, failed: [] };

      const queued: UploadJob[] = list.map((file) => ({
        id: nextId(),
        name: file.name,
        size: file.size,
        percent: 0,
        status: 'uploading',
      }));
      queued.forEach((job, index) => {
        files.current.set(job.id, list[index]);
      });
      setJobs((current) => [...current, ...queued]);

      let uploaded = 0;
      const failed: string[] = [];
      let next = 0;
      const worker = async () => {
        while (next < list.length) {
          const index = next;
          next += 1;
          const outcome = await upload(queued[index].id, list[index]);
          if (outcome === 'done') uploaded += 1;
          // A cancel is the user's own doing — it needs no toast and no row.
          else if (outcome === 'error') failed.push(list[index].name);
        }
      };
      await Promise.all(Array.from({ length: Math.min(UPLOAD_CONCURRENCY, list.length) }, worker));

      settleBatch(uploaded);
      return { uploaded, failed };
    },
    [upload, settleBatch],
  );

  const retry = useCallback(
    async (id: string): Promise<boolean> => {
      const file = files.current.get(id);
      if (!file) return false;
      patch(id, { percent: 0, status: 'uploading', reason: undefined });
      const outcome = await upload(id, file);
      settleBatch(outcome === 'done' ? 1 : 0);
      return outcome === 'done';
    },
    [patch, upload, settleBatch],
  );

  const forget = useCallback((id: string) => {
    files.current.delete(id);
    setJobs((current) => current.filter((j) => j.id !== id));
  }, []);

  /** Stop an in-flight upload and drop its row. The bytes already sent are lost. */
  const cancel = useCallback(
    (id: string) => {
      requests.current.get(id)?.abort();
      forget(id);
    },
    [forget],
  );

  // Derived, not tracked separately: a ref would not re-render the button and
  // a second state field could disagree with the rows on screen.
  const busy = jobs.some((j) => j.status === 'uploading');

  return { jobs, start, retry, cancel, dismiss: forget, busy };
}
