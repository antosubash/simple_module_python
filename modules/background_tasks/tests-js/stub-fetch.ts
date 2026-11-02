import { vi } from 'vitest';

// A 204 must carry no body: `new Response('{}', { status: 204 })` throws.
export function stubFetch(status: number, body: unknown = {}) {
  const fetchMock = vi.fn(
    async () => new Response(status === 204 ? null : JSON.stringify(body), { status }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** The `(path+query, method)` of every call: the typed client passes `Request` objects. */
export function requestsOf(fetchMock: ReturnType<typeof stubFetch>) {
  return (fetchMock.mock.calls as unknown as [Request][]).map(([req]) => {
    const url = new URL(req.url);
    return { url: `${url.pathname}${url.search}`, method: req.method };
  });
}
