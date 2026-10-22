/**
 * Typed JSON calls to a module's `/api` routes (#504).
 *
 * `createApi<paths>()` wraps `openapi-fetch` with the session conventions:
 * same-origin credentials, `Accept: application/json`, and the `csrfToken`
 * shared prop echoed as `X-CSRF-Token` on POST/PUT/PATCH/DELETE. Wrap a call
 * in `apiResult()` for the `{ ok, status, data, detail, fieldErrors }` shape.
 * `apiFetch()` is the untyped twin for routes outside the OpenAPI document
 * (`/setup/*`) and multipart uploads.
 */
import createClient, { type Client, type ClientOptions, type Middleware } from 'openapi-fetch';
import { type ApiResult, failure, NETWORK_FAILURE, readBody, success } from './api-result';
import { currentCsrfToken } from './csrf-token';

export { type ApiResult, apiResult, type FieldErrors, NETWORK_FAILURE } from './api-result';
export { currentCsrfToken, setCsrfToken } from './csrf-token';

const CSRF_HEADER = 'X-CSRF-Token';
const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** The token is the session's: never hand it to another origin. */
function sameOrigin(url: string): boolean {
  const origin = globalThis.location?.origin;
  try {
    return !!origin && new URL(url).origin === origin;
  } catch {
    return false;
  }
}

function prepare(request: Request, token: () => string | null | undefined): Request {
  if (!request.headers.has('Accept')) request.headers.set('Accept', 'application/json');
  if (!UNSAFE.has(request.method) || request.headers.has(CSRF_HEADER)) return request;
  const value = sameOrigin(request.url) ? token() : null;
  if (value) request.headers.set(CSRF_HEADER, value);
  return request;
}

export interface ApiOptions extends Omit<ClientOptions, 'fetch'> {
  /** Token source for this client; defaults to the `csrfToken` shared prop. */
  csrfToken?: () => string | null | undefined;
}

/** An `openapi-fetch` client for a module's generated `paths`. */
export function createApi<Paths extends {}>(options: ApiOptions = {}): Client<Paths> {
  const { csrfToken, ...rest } = options;
  const client = createClient<Paths>({
    credentials: 'same-origin',
    baseUrl: globalThis.location?.origin ?? '',
    ...rest,
    // Late-bound so a stubbed `globalThis.fetch` (tests) is honoured.
    fetch: (input) => globalThis.fetch(input),
  });
  const middleware: Middleware = {
    onRequest: ({ request }) => prepare(request, csrfToken ?? currentCsrfToken),
  };
  client.use(middleware);
  return client;
}

export interface ApiFetchInit extends RequestInit {
  /** Serialised as the JSON body (sets `Content-Type`). */
  json?: unknown;
}

/** Untyped call with the same conventions and result shape as `createApi`. */
export async function apiFetch<T = unknown>(
  url: string,
  init: ApiFetchInit = {},
): Promise<ApiResult<T>> {
  const { json, ...rest } = init;
  const headers = new Headers(rest.headers);
  if (json !== undefined) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    const request = new Request(new URL(url, globalThis.location?.href), {
      credentials: 'same-origin',
      ...rest,
      headers,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
    response = await globalThis.fetch(prepare(request, currentCsrfToken));
  } catch {
    return failure<T>(NETWORK_FAILURE, null);
  }
  const body = await readBody(response);
  return response.ok ? success(response.status, body as T) : failure<T>(response.status, body);
}
