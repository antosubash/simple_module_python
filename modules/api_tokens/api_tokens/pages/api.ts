/**
 * JSON calls to the api_tokens endpoints.
 *
 * Plain `fetch`, not Inertia's router: creating a token must hand the page
 * its secret as data, once, which a redirect cannot carry. Every mutation
 * echoes the session's CSRF token (`RequiresCsrf` on the server).
 */

export interface ApiResult<T> {
  ok: boolean;
  data: T | null;
  /** The server's message when it sent a plain string; null otherwise. */
  detail: string | null;
}

export async function postJson<T>(
  url: string,
  csrfToken: string,
  body?: unknown,
): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    return { ok: false, data: null, detail: null };
  }
  const json = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = json && typeof json.detail === 'string' ? json.detail : null;
    return { ok: false, data: null, detail };
  }
  return { ok: true, data: json as T, detail: null };
}
