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
  return reasonFromBody(parsed);
}

/** `parseFailureReason` for a body that is already parsed (the API client's `error`). */
export function reasonFromBody(parsed: unknown): string | undefined {
  const detail = (parsed as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail || undefined;
  const message = (detail as { message?: unknown } | null)?.message;
  return typeof message === 'string' && message ? message : undefined;
}

/** A resumable upload that stopped, with the server's reason when it gave one. */
export class UploadFailedError extends Error {
  constructor(
    readonly status: number | undefined,
    readonly reason?: string,
  ) {
    super(reason ?? `upload failed (${status ?? 'network'})`);
  }
}

/** The user (or a sibling part's failure) stopped the upload on purpose. */
export class UploadAbortedError extends Error {}
