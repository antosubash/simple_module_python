import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const handlers = vi.hoisted(
  () => ({}) as Record<string, (event: { detail: { page: unknown } }) => void>,
);
vi.mock('@inertiajs/react', () => ({
  router: {
    on: (name: string, cb: (event: { detail: { page: unknown } }) => void) => {
      handlers[name] = cb;
      return () => {};
    },
  },
}));

import { apiFetch, apiResult, createApi, currentCsrfToken, setCsrfToken } from './api';

interface paths {
  '/api/things/{id}': {
    get: {
      parameters: { path: { id: string } };
      responses: { 200: { content: { 'application/json': { id: string } } } };
    };
    post: {
      parameters: { path: { id: string } };
      requestBody: { content: { 'application/json': { name: string } } };
      responses: {
        201: { content: { 'application/json': { id: string; name: string } } };
        422: { content: { 'application/json': unknown } };
      };
    };
  };
}

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(
    async (_input: Request) =>
      new Response(body === undefined ? null : JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const sent = (mock: ReturnType<typeof stubFetch>) => mock.mock.calls[0][0];

beforeEach(() => setCsrfToken('tok-1'));
afterEach(() => {
  vi.unstubAllGlobals();
  setCsrfToken(undefined);
  document.body.innerHTML = '';
});

describe('createApi', () => {
  it('sends the CSRF token, same-origin credentials and Accept on a POST', async () => {
    const fetchMock = stubFetch(201, { id: '1', name: 'a' });
    const api = createApi<paths>();
    const result = await apiResult(
      api.POST('/api/things/{id}', { params: { path: { id: '1' } }, body: { name: 'a' } }),
    );
    expect(result).toMatchObject({ ok: true, status: 201, data: { id: '1', name: 'a' } });
    const request = sent(fetchMock);
    expect(new URL(request.url).pathname).toBe('/api/things/1');
    expect(request.method).toBe('POST');
    expect(request.headers.get('X-CSRF-Token')).toBe('tok-1');
    expect(request.headers.get('Accept')).toBe('application/json');
    expect(request.credentials).toBe('same-origin');
    expect(await request.json()).toEqual({ name: 'a' });
  });

  it('never sends the token on a safe method', async () => {
    const fetchMock = stubFetch(200, { id: '1' });
    await createApi<paths>().GET('/api/things/{id}', { params: { path: { id: '1' } } });
    expect(sent(fetchMock).headers.has('X-CSRF-Token')).toBe(false);
  });

  it('prefers a per-client token source and keeps an explicit header', async () => {
    const fetchMock = stubFetch(201, { id: '1', name: 'a' });
    const api = createApi<paths>({ csrfToken: () => 'page-prop' });
    await api.POST('/api/things/{id}', { params: { path: { id: '1' } }, body: { name: 'a' } });
    expect(sent(fetchMock).headers.get('X-CSRF-Token')).toBe('page-prop');

    const second = stubFetch(201, { id: '1', name: 'a' });
    await createApi<paths>().POST('/api/things/{id}', {
      params: { path: { id: '1' } },
      body: { name: 'a' },
      headers: { 'X-CSRF-Token': 'explicit' },
    });
    expect(sent(second).headers.get('X-CSRF-Token')).toBe('explicit');
  });

  it('sends no token header when none is known (anonymous page)', async () => {
    setCsrfToken(null);
    const fetchMock = stubFetch(201, { id: '1', name: 'a' });
    await createApi<paths>().POST('/api/things/{id}', {
      params: { path: { id: '1' } },
      body: { name: 'a' },
    });
    expect(sent(fetchMock).headers.has('X-CSRF-Token')).toBe(false);
  });
});

describe('apiResult', () => {
  const call = () =>
    createApi<paths>().POST('/api/things/{id}', {
      params: { path: { id: '1' } },
      body: { name: '' },
    });

  it('exposes a string detail', async () => {
    stubFetch(409, { detail: 'slug_taken' });
    const result = await apiResult(call());
    expect(result).toMatchObject({ ok: false, status: 409, detail: 'slug_taken', data: null });
  });

  it('maps 422 validation errors by the last loc element', async () => {
    stubFetch(422, {
      detail: [
        { loc: ['body', 'name'], msg: 'too short' },
        { loc: ['body', 'items', 0], msg: 'bad item' },
      ],
    });
    const result = await apiResult(call());
    expect(result.ok).toBe(false);
    expect(result.detail).toBeNull();
    expect(result.fieldErrors).toEqual({ name: 'too short', '0': 'bad item' });
  });

  it('turns a network failure into status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    expect(await apiResult(call())).toMatchObject({ ok: false, status: 0, detail: null });
  });
});

describe('apiFetch', () => {
  it('serialises json and normalises the result', async () => {
    const fetchMock = stubFetch(200, { saved: true });
    const result = await apiFetch<{ saved: boolean }>('/setup/save', {
      method: 'PUT',
      json: { value: 'x' },
    });
    expect(result).toMatchObject({ ok: true, data: { saved: true } });
    const request = sent(fetchMock);
    expect(request.headers.get('Content-Type')).toBe('application/json');
    expect(request.headers.get('X-CSRF-Token')).toBe('tok-1');
    expect(await request.json()).toEqual({ value: 'x' });
  });

  it('leaves a multipart body alone', async () => {
    const fetchMock = stubFetch(204, undefined);
    const body = new FormData();
    body.append('file', new Blob(['x']), 'a.png');
    const result = await apiFetch('/api/upload', { method: 'POST', body });
    expect(result).toMatchObject({ ok: true, status: 204, data: null });
    expect(sent(fetchMock).headers.get('Content-Type')).toMatch(/^multipart\/form-data/);
  });

  it('keeps a non-JSON error body as text and a network error as status 0', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('boom', { status: 500 })),
    );
    expect(await apiFetch('/x')).toMatchObject({ ok: false, status: 500, error: 'boom' });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    expect(await apiFetch('/x')).toMatchObject({ ok: false, status: 0 });
  });
});

describe('cross-origin URLs', () => {
  it.each([
    ['an absolute cross-origin URL', 'https://evil.example/steal', false],
    ['a protocol-relative URL', '//evil.example/steal', false],
    ['a same-origin absolute URL', `${window.location.origin}/api/x`, true],
  ])('apiFetch to %s sends the token only when same-origin', async (_label, url, expected) => {
    const fetchMock = stubFetch(200, {});
    await apiFetch(url, { method: 'POST', json: {} });
    expect(sent(fetchMock).headers.get('X-CSRF-Token')).toBe(expected ? 'tok-1' : null);
  });

  it('createApi with a foreign baseUrl never sends the token', async () => {
    const fetchMock = stubFetch(201, { id: '1', name: 'a' });
    await createApi<paths>({ baseUrl: 'https://evil.example' }).POST('/api/things/{id}', {
      params: { path: { id: '1' } },
      body: { name: 'a' },
    });
    expect(sent(fetchMock).headers.has('X-CSRF-Token')).toBe(false);
  });
});

describe('currentCsrfToken', () => {
  it('tracks the shared prop across Inertia visits', () => {
    handlers.navigate({ detail: { page: { props: { csrfToken: 'from-nav' } } } });
    expect(currentCsrfToken()).toBe('from-nav');
    handlers.success({ detail: { page: { props: {} } } });
    expect(currentCsrfToken()).toBeNull();
  });

  it('falls back to the page embedded in the document', () => {
    setCsrfToken(undefined);
    document.body.innerHTML = `<script data-page="app" type="application/json">${JSON.stringify({
      props: { csrfToken: 'from-dom' },
    })}</script>`;
    expect(currentCsrfToken()).toBe('from-dom');
  });
});
