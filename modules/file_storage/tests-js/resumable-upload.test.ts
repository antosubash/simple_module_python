import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import {
  discardSession,
  findSession,
  PART_CONCURRENCY,
  runResumable,
} from '../file_storage/pages/resumable-upload';
import { resumeKey } from '../file_storage/pages/resume-store';
import { UploadAbortedError, UploadFailedError } from '../file_storage/pages/upload-errors';

const PART = 10;

interface PutCall {
  url: string;
  size: number;
}

/** A tiny in-memory server: sessions over fetch, part PUTs over XHR. */
class FakeServer {
  calls: string[] = [];
  puts: PutCall[] = [];
  held = new Map<number, string>();
  /** Status to answer each PUT with, per part, consumed in order; default 200. */
  putStatuses = new Map<number, number[]>();
  inFlight = 0;
  maxInFlight = 0;
  completeBody: unknown = null;
  completeStatus = 200;
  total = 0;

  fetch = async (request: Request): Promise<Response> => {
    const method = request.method;
    const url = new URL(request.url).pathname;
    const init = { body: await request.text() };
    this.calls.push(`${method} ${url}`);
    const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
    if (method === 'POST' && url === '/api/file-storage/uploads') {
      const body = JSON.parse(init.body as string);
      this.total = body.total_size;
      return json(201, this.session());
    }
    if (method === 'GET') return json(200, this.session());
    if (method === 'DELETE') return new Response(null, { status: 204 });
    if (url.endsWith('/part-urls')) {
      const { parts } = JSON.parse(init.body as string);
      return json(200, {
        direct: true,
        urls: Object.fromEntries(
          parts.map((n: number) => [String(n), `https://s3.test/part/${n}`]),
        ),
      });
    }
    if (url.endsWith('/complete')) {
      this.completeBody = JSON.parse(init.body as string);
      return json(this.completeStatus, {
        detail: { code: 'x', message: 'parts do not match' },
      });
    }
    throw new Error(`unexpected ${method} ${url}`);
  };

  session() {
    return {
      id: 'sess-1',
      total_size: this.total,
      part_size: PART,
      total_parts: Math.ceil(this.total / PART),
      status: 'active',
      parts: [...this.held].map(([no, etag]) => ({ no, etag, size: PART })),
    };
  }
}

let server: FakeServer;

class FakeXhr {
  status = 0;
  responseText = '';
  private handlers: Record<string, () => void> = {};
  private url = '';
  private aborted = false;
  upload = { addEventListener: (_t: string, _fn: unknown) => {} };

  open(_method: string, url: string) {
    this.url = url;
  }
  addEventListener(type: string, fn: () => void) {
    this.handlers[type] = fn;
  }
  getResponseHeader(name: string) {
    return name === 'ETag' ? `"etag-${this.url.split('/').pop()}"` : null;
  }
  abort() {
    this.aborted = true;
    this.handlers.abort?.();
  }
  send(blob: Blob) {
    const n = Number(this.url.split('/').pop());
    server.puts.push({ url: this.url, size: blob.size });
    server.inFlight += 1;
    server.maxInFlight = Math.max(server.maxInFlight, server.inFlight);
    setTimeout(() => {
      server.inFlight -= 1;
      if (this.aborted) return;
      this.status = server.putStatuses.get(n)?.shift() ?? 200;
      this.handlers.load?.();
    }, 1);
  }
}

function bigFile(parts: number, name = 'movie.bin') {
  return new File([new Uint8Array(PART * parts - 3)], name, { lastModified: 1234 });
}

const OPTIONS = (signal = new AbortController().signal) => ({
  signal,
  onProgress: vi.fn(),
  backoffMs: 0,
});

beforeEach(() => {
  server = new FakeServer();
  vi.stubGlobal('fetch', server.fetch);
  vi.stubGlobal('XMLHttpRequest', FakeXhr);
  window.localStorage.clear();
});

afterEach(() => vi.unstubAllGlobals());

describe('runResumable', () => {
  test('sends every part, at most four at once, then completes with the etags', async () => {
    const file = bigFile(9);
    const options = OPTIONS();
    await runResumable(file, options);

    expect(server.puts).toHaveLength(9);
    expect(server.maxInFlight).toBeLessThanOrEqual(PART_CONCURRENCY);
    expect(server.maxInFlight).toBeGreaterThan(1);
    // The last part is the remainder, not a full part.
    expect(server.puts.find((p) => p.url.endsWith('/9'))?.size).toBe(PART - 3);
    const body = server.completeBody as { parts: { n: number; etag: string }[] };
    expect(body.parts).toHaveLength(9);
    expect(body.parts[0]).toEqual({ n: 1, etag: '"etag-1"' });
    // Progress ends at the whole file.
    expect(options.onProgress).toHaveBeenLastCalledWith(file.size, file.size);
  });

  test('remembers the session while running and forgets it once complete', async () => {
    const file = bigFile(2);
    const key = resumeKey(file);
    let seen: string | null = null;
    server.putStatuses.set(1, [200]);
    const original = server.fetch;
    vi.stubGlobal('fetch', async (request: Request) => {
      if (request.url.endsWith('/complete')) seen = window.localStorage.getItem(key);
      return original(request);
    });

    await runResumable(file, OPTIONS());

    expect(seen).toBe('sess-1');
    expect(window.localStorage.getItem(key)).toBeNull();
  });

  test('skips the parts the server already holds when resuming', async () => {
    const file = bigFile(4);
    server.total = file.size;
    server.held = new Map([
      [1, '"e1"'],
      [3, '"e3"'],
    ]);

    await runResumable(file, OPTIONS(), server.session() as never);

    expect(server.puts.map((p) => p.url.split('/').pop()).sort()).toEqual(['2', '4']);
    expect(server.calls.some((c) => c === 'POST /api/file-storage/uploads')).toBe(false);
    const body = server.completeBody as { parts: { n: number; etag: string }[] };
    expect(body.parts.map((p) => p.n).sort()).toEqual([1, 2, 3, 4]);
  });

  test('retries a failing part with a fresh URL each time', async () => {
    server.putStatuses.set(2, [500, 403]);
    await runResumable(bigFile(3), OPTIONS());

    const urlRequests = server.calls.filter((c) => c.endsWith('/part-urls'));
    expect(urlRequests).toHaveLength(3 + 2);
    expect(server.puts.filter((p) => p.url.endsWith('/2'))).toHaveLength(3);
  });

  test('gives up on a part after four attempts and keeps the session to resume', async () => {
    server.putStatuses.set(1, [500, 500, 500, 500]);
    const file = bigFile(1);

    await expect(runResumable(file, OPTIONS())).rejects.toBeInstanceOf(UploadFailedError);

    expect(server.puts).toHaveLength(4);
    expect(window.localStorage.getItem(resumeKey(file))).toBe('sess-1');
  });

  test('does not retry a part the server refused on its merits', async () => {
    server.putStatuses.set(1, [400]);
    await expect(runResumable(bigFile(1), OPTIONS())).rejects.toMatchObject({ status: 400 });
    expect(server.puts).toHaveLength(1);
  });

  test("surfaces the server's reason when completing fails", async () => {
    server.completeStatus = 409;
    await expect(runResumable(bigFile(1), OPTIONS())).rejects.toMatchObject({
      status: 409,
      reason: 'parts do not match',
    });
  });

  test('cancelling stops the upload with an abort, not a failure', async () => {
    const controller = new AbortController();
    const running = runResumable(bigFile(8), OPTIONS(controller.signal));
    setTimeout(() => controller.abort(), 0);
    await expect(running).rejects.toBeInstanceOf(UploadAbortedError);
  });
});

describe('cancelling while the session is being created', () => {
  test('releases the session the create resolved with', async () => {
    const controller = new AbortController();
    const file = bigFile(3);
    const running = runResumable(file, OPTIONS(controller.signal));
    controller.abort(); // the POST is in flight; no session id exists yet
    await expect(running).rejects.toBeInstanceOf(UploadAbortedError);
    expect(server.calls).toContain('DELETE /api/file-storage/uploads/sess-1');
    expect(server.puts).toHaveLength(0);
    expect(window.localStorage.getItem(resumeKey(file))).toBeNull();
  });
});

describe('findSession / discardSession', () => {
  test('finds the open session stored for the same file', async () => {
    const file = bigFile(3);
    server.total = file.size;
    window.localStorage.setItem(resumeKey(file), 'sess-1');
    expect(await findSession(file)).toMatchObject({ id: 'sess-1', status: 'active' });
  });

  test('a different file finds nothing', async () => {
    window.localStorage.setItem(resumeKey(bigFile(3, 'other.bin')), 'sess-1');
    expect(await findSession(bigFile(3))).toBeNull();
  });

  test('a session the server no longer knows is forgotten', async () => {
    const file = bigFile(3);
    window.localStorage.setItem(resumeKey(file), 'gone');
    vi.stubGlobal('fetch', async () => new Response('{}', { status: 404 }));
    expect(await findSession(file)).toBeNull();
    expect(window.localStorage.getItem(resumeKey(file))).toBeNull();
  });

  test('a network failure keeps the stored id for next time', async () => {
    const file = bigFile(3);
    window.localStorage.setItem(resumeKey(file), 'sess-1');
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('offline');
    });
    expect(await findSession(file)).toBeNull();
    expect(window.localStorage.getItem(resumeKey(file))).toBe('sess-1');
  });

  test('works with storage unavailable', async () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(await findSession(bigFile(2))).toBeNull();
    spy.mockRestore();
  });

  test('discarding aborts the session and clears the key', async () => {
    const file = bigFile(2);
    window.localStorage.setItem(resumeKey(file), 'sess-1');
    await discardSession(file, 'sess-1');
    expect(server.calls).toContain('DELETE /api/file-storage/uploads/sess-1');
    expect(window.localStorage.getItem(resumeKey(file))).toBeNull();
  });
});
