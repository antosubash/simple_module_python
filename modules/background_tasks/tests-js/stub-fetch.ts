import { vi } from 'vitest';

// A 204 must carry no body: `new Response('{}', { status: 204 })` throws.
export function stubFetch(status: number, body: unknown = {}) {
  const fetchMock = vi.fn(
    async () => new Response(status === 204 ? null : JSON.stringify(body), { status }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}
