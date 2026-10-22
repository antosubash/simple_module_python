import { apiFetch, NETWORK_FAILURE } from '@simple-module-py/ui/lib/api';
import { clearSessionId, loadSessionId, saveSessionId } from './resume-store';
import {
  parseFailureReason,
  reasonFromBody,
  UploadAbortedError,
  UploadFailedError,
} from './upload-errors';

/** Parts in flight at once, per file. */
export const PART_CONCURRENCY = 4;
const MAX_ATTEMPTS = 4;
const BACKOFF_MS = 500;
const BASE = '/api/file-storage/uploads';

export interface RemotePart {
  no: number;
  etag: string;
  size: number;
}

export interface RemoteSession {
  id: string;
  total_size: number;
  part_size: number;
  total_parts: number;
  status: 'active' | 'completed' | 'aborted';
  parts: RemotePart[];
}

export interface RunOptions {
  /** Called with bytes sent so far and the file's size. */
  onProgress: (sent: number, total: number) => void;
  signal: AbortSignal;
  /** Milliseconds before retry 1; doubles each time. Tests pass 0. */
  backoffMs?: number;
}

/**
 * One JSON call to the uploads API. These routes are addressed dynamically
 * (session id in the path, one helper for every verb), so they go through the
 * untyped `apiFetch`; a failure becomes an `UploadFailedError` carrying the
 * status (`undefined` when the request never reached the server) and the
 * server's own reason.
 */
async function call<T>(method: string, url: string, json?: unknown): Promise<T> {
  const result = await apiFetch<T>(url, { method, json });
  if (!result.ok) {
    throw new UploadFailedError(
      result.status === NETWORK_FAILURE ? undefined : result.status,
      reasonFromBody(result.error),
    );
  }
  return result.data;
}

/** The stored session for this file, if the server still has it open. */
export async function findSession(file: File): Promise<RemoteSession | null> {
  const id = loadSessionId(file);
  if (!id) return null;
  try {
    const session = await call<RemoteSession>('GET', `${BASE}/${id}`);
    if (session.status === 'active' && session.total_size === file.size) return session;
  } catch (error) {
    // A network blip says nothing about the session; keep the id for next time.
    if (error instanceof UploadFailedError && error.status === undefined) return null;
  }
  clearSessionId(file);
  return null;
}

/** Abort the server session and forget it; best effort. */
export async function discardSession(file: File, id: string): Promise<void> {
  clearSessionId(file);
  try {
    await call('DELETE', `${BASE}/${id}`);
  } catch {
    // The reaper collects it at expiry.
  }
}

function createSession(file: File): Promise<RemoteSession> {
  return call<RemoteSession>('POST', BASE, {
    filename: file.name,
    content_type: file.type || 'application/octet-stream',
    total_size: file.size,
  });
}

/** PUT one blob; resolves with the ETag the store (or the app) answered. */
function putBlob(
  url: string,
  blob: Blob,
  signal: AbortSignal,
  onProgress: (loaded: number) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const onAbort = () => xhr.abort();
    signal.addEventListener('abort', onAbort);
    const done = () => signal.removeEventListener('abort', onAbort);
    xhr.open('PUT', url);
    xhr.upload.addEventListener('progress', (event) => onProgress(event.loaded));
    xhr.addEventListener('load', () => {
      done();
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new UploadFailedError(xhr.status, parseFailureReason(xhr.responseText)));
        return;
      }
      // S3 answers with an ETag header (if its CORS rule exposes it); the app's
      // relay answers with the part as JSON. A missing ETag is tolerated: the
      // server lists parts itself when completing.
      let etag = xhr.getResponseHeader('ETag') ?? '';
      if (!etag) {
        try {
          etag = (JSON.parse(xhr.responseText) as { etag?: string }).etag ?? '';
        } catch {
          // not JSON
        }
      }
      resolve(etag);
    });
    xhr.addEventListener('error', () => {
      done();
      reject(new UploadFailedError(undefined));
    });
    xhr.addEventListener('abort', () => {
      done();
      reject(new UploadAbortedError());
    });
    xhr.send(blob);
  });
}

/** Retrying cannot help a request the server refused on its merits. */
function isPermanent(error: unknown): boolean {
  if (!(error instanceof UploadFailedError) || error.status === undefined) return false;
  // 403 is a presigned URL that expired mid-retry; 408/429 are "try later".
  return error.status < 500 && ![403, 408, 429].includes(error.status);
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Upload `file` in parts through a server session, resuming `existing` if given.
 *
 * Parts already held by the server are skipped. Each part is retried with
 * exponential backoff, asking for a fresh URL every attempt so an expired
 * presign never strands it. Resolves once the server has assembled the file;
 * rejects with `UploadFailedError` (session left resumable) or
 * `UploadAbortedError`.
 */
export async function runResumable(
  file: File,
  options: RunOptions,
  existing?: RemoteSession | null,
): Promise<void> {
  const session = existing ?? (await createSession(file));
  if (options.signal.aborted) {
    // Cancelled while the create was in flight: the cancel found no session id
    // to discard, so this is the only place that can release it.
    if (!existing) await discardSession(file, session.id);
    throw new UploadAbortedError();
  }
  saveSessionId(file, session.id);

  const etags = new Map<number, string>(session.parts.map((p) => [p.no, p.etag]));
  const sent = new Map<number, number>(
    session.parts.map((p) => [p.no, Math.min(p.size, file.size)]),
  );
  const report = () => {
    let total = 0;
    sent.forEach((bytes) => {
      total += bytes;
    });
    options.onProgress(Math.min(total, file.size), file.size);
  };
  report();

  const inner = new AbortController();
  const forward = () => inner.abort();
  options.signal.addEventListener('abort', forward);

  const pending: number[] = [];
  for (let n = 1; n <= session.total_parts; n += 1) if (!etags.has(n)) pending.push(n);

  const uploadPart = async (n: number) => {
    const start = (n - 1) * session.part_size;
    const blob = file.slice(start, Math.min(start + session.part_size, file.size));
    for (let attempt = 0; ; attempt += 1) {
      if (inner.signal.aborted) throw new UploadAbortedError();
      try {
        const { urls } = await call<{ urls: Record<string, string> }>(
          'POST',
          `${BASE}/${session.id}/part-urls`,
          { parts: [n] },
        );
        const etag = await putBlob(urls[String(n)], blob, inner.signal, (loaded) => {
          sent.set(n, loaded);
          report();
        });
        etags.set(n, etag);
        sent.set(n, blob.size);
        report();
        return;
      } catch (error) {
        sent.set(n, 0);
        if (error instanceof UploadAbortedError || isPermanent(error)) throw error;
        if (attempt + 1 >= MAX_ATTEMPTS) throw error;
        await sleep((options.backoffMs ?? BACKOFF_MS) * 2 ** attempt);
      }
    }
  };

  const worker = async () => {
    for (let n = pending.shift(); n !== undefined; n = pending.shift()) await uploadPart(n);
  };

  try {
    await Promise.all(Array.from({ length: PART_CONCURRENCY }, worker));
    await call('POST', `${BASE}/${session.id}/complete`, {
      parts: [...etags].filter(([, etag]) => etag).map(([n, etag]) => ({ n, etag })),
    });
  } catch (error) {
    // A sibling's failure aborts the rest; the user's cancel does too.
    inner.abort();
    if (options.signal.aborted) throw new UploadAbortedError();
    throw error;
  } finally {
    options.signal.removeEventListener('abort', forward);
  }
  clearSessionId(file);
}
