/**
 * The one result shape every `api.*` / `apiFetch` call resolves to (#504).
 * No English strings here: callers map `detail` codes and fall back to their
 * own translated copy (see `useApiErrorToast`).
 */

export type FieldErrors = Record<string, string>;

export type ApiResult<T> =
  | { ok: true; status: number; data: T; detail: null; fieldErrors: FieldErrors; error: null }
  | {
      ok: false;
      /** 0 when the request never reached the server. */
      status: number;
      data: null;
      /** The server's `detail` when it is a string (a message or a stable code). */
      detail: string | null;
      /** 422 validation errors: the last `loc` element → `msg`. */
      fieldErrors: FieldErrors;
      /** The parsed error body, for codes that carry more than `detail`. */
      error: unknown;
    };

/** `status` of a request that never reached the server. */
export const NETWORK_FAILURE = 0;

function fieldErrorsOf(status: number, body: unknown): FieldErrors {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (status !== 422 || !Array.isArray(detail)) return {};
  const out: FieldErrors = {};
  for (const item of detail as { loc?: unknown[]; msg?: unknown }[]) {
    const field = item?.loc?.[item.loc.length - 1];
    if (field !== undefined && typeof item.msg === 'string') out[String(field)] = item.msg;
  }
  return out;
}

export function success<T>(status: number, data: T): ApiResult<T> {
  return { ok: true, status, data, detail: null, fieldErrors: {}, error: null };
}

export function failure<T>(status: number, body: unknown): ApiResult<T> {
  const detail = (body as { detail?: unknown } | null)?.detail;
  return {
    ok: false,
    status,
    data: null,
    detail: typeof detail === 'string' ? detail : null,
    fieldErrors: fieldErrorsOf(status, body),
    error: body ?? null,
  };
}

/** Normalise an `openapi-fetch` call; a rejected fetch becomes `status: 0`. */
export async function apiResult<T, E>(
  call: Promise<{ data?: T; error?: E; response: Response }>,
): Promise<ApiResult<T>> {
  try {
    const { data, error, response } = await call;
    if (!response.ok) return failure<T>(response.status, error);
    return success(response.status, data as T);
  } catch {
    return failure<T>(NETWORK_FAILURE, null);
  }
}

/** Parse a raw response body: JSON when it is JSON, the text otherwise, null when empty. */
export async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
