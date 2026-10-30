import { router } from '@inertiajs/react';
import { useCallback, useRef, useState } from 'react';

import { RELOAD_PROPS, ROUTES, UPLOAD_CONCURRENCY } from './constants';
import type { RemoteSession } from './resumable-upload';
import { discardSession, findSession, runResumable } from './resumable-upload';
import { loadSessionId } from './resume-store';
import { parseFailureReason, UploadAbortedError, UploadFailedError } from './upload-errors';

export { parseFailureReason };

export interface UploadJob {
  id: string;
  name: string;
  size: number;
  /** 0–100. Stays at 100 while the server finishes writing to the backend. */
  percent: number;
  /** `resumable`: a partly-sent copy of this file is on the server, awaiting a choice. */
  status: 'uploading' | 'done' | 'error' | 'resumable';
  /** Why it failed, in the server's words. Undefined for a transport failure. */
  reason?: string;
}

type Outcome = 'done' | 'error' | 'canceled' | 'paused';

export interface UploadQueueOptions {
  /** Files larger than this go through a resumable session; null/undefined: never. */
  directThresholdBytes?: number | null;
}

let counter = 0;
function nextId(): string {
  counter += 1;
  return `upload-${counter}`;
}

/**
 * Uploads files with bounded concurrency, reporting byte progress per file.
 *
 * Uses XMLHttpRequest rather than fetch deliberately: fetch exposes no upload
 * progress events in any current browser, and a large file uploading behind a
 * spinner with no feedback is the exact complaint this replaces.
 *
 * The queue keeps the `File` object while its row remains, so a failed row
 * can be retried from the row itself — the alternative is asking the person to
 * find the file on disk again to answer a transient 502.
 */
export function useUploadQueue({ directThresholdBytes }: UploadQueueOptions = {}) {
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const files = useRef(new Map<string, File>());
  const requests = useRef(new Map<string, XMLHttpRequest>());
  // Resumable jobs: one controller per running upload, and the server session
  // a job is waiting on while the user decides between resuming and starting over.
  const controllers = useRef(new Map<string, AbortController>());
  const waiting = useRef(new Map<string, RemoteSession>());

  const patch = useCallback((id: string, changes: Partial<UploadJob>) => {
    setJobs((current) => current.map((j) => (j.id === id ? { ...j, ...changes } : j)));
  }, []);

  const uploadInParts = useCallback(
    async (jobId: string, file: File, session: RemoteSession | null): Promise<Outcome> => {
      const controller = new AbortController();
      controllers.current.set(jobId, controller);
      patch(jobId, { status: 'uploading', reason: undefined });
      try {
        await runResumable(
          file,
          {
            signal: controller.signal,
            onProgress: (sent, total) =>
              patch(jobId, { percent: Math.round((sent / total) * 100) }),
          },
          session,
        );
        patch(jobId, { percent: 100, status: 'done' });
        return 'done';
      } catch (error) {
        if (error instanceof UploadAbortedError) return 'canceled';
        const reason = error instanceof UploadFailedError ? error.reason : undefined;
        patch(jobId, { status: 'error', reason });
        return 'error';
      } finally {
        controllers.current.delete(jobId);
      }
    },
    [patch],
  );

  /** A copy of this file is already on the server: let the user pick before sending more. */
  const maybePause = useCallback(
    async (jobId: string, file: File): Promise<RemoteSession | 'paused' | null> => {
      const session = await findSession(file);
      if (!files.current.has(jobId)) return null;
      if (!session || session.parts.length === 0) return session;
      const sent = session.parts.reduce((sum, part) => sum + part.size, 0);
      waiting.current.set(jobId, session);
      patch(jobId, { status: 'resumable', percent: Math.round((sent / file.size) * 100) });
      return 'paused';
    },
    [patch],
  );

  const uploadOnce = useCallback(
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

  const upload = useCallback(
    async (jobId: string, file: File, resumeAutomatically = false): Promise<Outcome> => {
      if (directThresholdBytes && file.size > directThresholdBytes) {
        const found = resumeAutomatically ? await findSession(file) : await maybePause(jobId, file);
        if (!files.current.has(jobId)) return 'canceled';
        if (found === 'paused') return 'paused';
        return uploadInParts(jobId, file, found);
      }
      return uploadOnce(jobId, file);
    },
    [directThresholdBytes, maybePause, uploadInParts, uploadOnce],
  );

  // Completed rows disappear once the reloaded table can *show* the real
  // record — dropping them before the reply lands leaves a gap where the
  // table still holds the pre-upload list, and a first upload into an
  // empty bucket flashes "No files yet". Failures stay until dismissed so
  // they can't go unnoticed, and anything still uploading stays too — a
  // second batch dropped while this reload is in flight must not have its
  // progress rows swept away by the first batch's cleanup.
  const settleBatch = useCallback((uploaded: number) => {
    const clearFinished = () =>
      setJobs((current) =>
        current.filter((job) => {
          if (job.status !== 'done') return true;
          files.current.delete(job.id);
          return false;
        }),
      );
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
          const jobId = queued[index].id;
          if (!files.current.has(jobId)) continue;
          const outcome = await upload(jobId, list[index]);
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
      // A failed resumable upload picks up where it stopped, without asking.
      const outcome = await upload(id, file, true);
      settleBatch(outcome === 'done' ? 1 : 0);
      return outcome === 'done';
    },
    [patch, upload, settleBatch],
  );

  const finishResumed = useCallback(
    async (id: string, run: (file: File) => Promise<Outcome>): Promise<boolean> => {
      const file = files.current.get(id);
      if (!file) return false;
      const outcome = await run(file);
      settleBatch(outcome === 'done' ? 1 : 0);
      return outcome === 'done';
    },
    [settleBatch],
  );

  /** Continue the partly-sent copy found on the server. */
  const resume = useCallback(
    (id: string) => {
      const session = waiting.current.get(id) ?? null;
      waiting.current.delete(id);
      return finishResumed(id, (file) => uploadInParts(id, file, session));
    },
    [finishResumed, uploadInParts],
  );

  /** Throw the partly-sent copy away and send the file again from the beginning. */
  const startOver = useCallback(
    (id: string) => {
      const session = waiting.current.get(id);
      waiting.current.delete(id);
      patch(id, { percent: 0, status: 'uploading' });
      return finishResumed(id, async (file) => {
        if (session) await discardSession(file, session.id);
        return uploadInParts(id, file, null);
      });
    },
    [finishResumed, patch, uploadInParts],
  );

  const forget = useCallback((id: string) => {
    files.current.delete(id);
    waiting.current.delete(id);
    setJobs((current) => current.filter((j) => j.id !== id));
  }, []);

  /** Stop an in-flight upload and drop its row. The bytes already sent are lost. */
  const cancel = useCallback(
    (id: string) => {
      requests.current.get(id)?.abort();
      // A cancelled resumable upload is abandoned, not paused: free the server's parts.
      const controller = controllers.current.get(id);
      const file = files.current.get(id);
      const sessionId = file && controller ? loadSessionId(file) : null;
      controller?.abort();
      if (file && sessionId) void discardSession(file, sessionId);
      forget(id);
    },
    [forget],
  );

  // Derived, not tracked separately: a ref would not re-render the button and
  // a second state field could disagree with the rows on screen.
  const busy = jobs.some((j) => j.status === 'uploading');

  const actions = { cancel, retry, resume, startOver, dismiss: forget };
  return { jobs, start, retry, cancel, resume, startOver, dismiss: forget, actions, busy };
}
