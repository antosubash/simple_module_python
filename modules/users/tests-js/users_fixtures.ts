import { vi } from 'vitest';

/** Stub `fetch`; `respond` gets each Request the typed client (or `apiFetch`) sends. */
export function stubFetch(respond: (request: Request) => Response | Promise<Response>) {
  const mock = vi.fn(async (input: Request) => respond(input));
  vi.stubGlobal('fetch', mock);
  return mock;
}

export const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

/** Path, method, content type and raw body of the Request sent on call `index`. */
export async function sent(mock: ReturnType<typeof stubFetch>, index = 0) {
  const request = mock.mock.calls[index][0];
  return {
    path: new URL(request.url).pathname,
    method: request.method,
    contentType: request.headers.get('Content-Type'),
    credentials: request.credentials,
    text: await request.clone().text(),
  };
}
