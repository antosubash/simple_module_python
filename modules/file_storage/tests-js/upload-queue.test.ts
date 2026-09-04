import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

// The queue reloads the table after a successful upload. Running the
// `onFinish` callback synchronously is what the real router does once the
// visit lands, and it is what clears the finished rows.
vi.mock('@inertiajs/react', () => ({
  router: {
    reload: vi.fn((options?: { onFinish?: () => void }) => options?.onFinish?.()),
  },
}));

import { parseFailureReason, useUploadQueue } from '../file_storage/pages/upload-queue';

/** Enough XMLHttpRequest for the queue: open/send/abort plus the four events. */
class FakeXhr {
  static instances: FakeXhr[] = [];

  status = 0;
  responseText = '';
  aborted = false;
  private handlers: Record<string, (() => void) | undefined> = {};
  private progress:
    | ((event: { lengthComputable: boolean; loaded: number; total: number }) => void)
    | undefined;

  upload = {
    addEventListener: (_type: string, fn: (event: never) => void) => {
      this.progress = fn as never;
    },
  };

  constructor() {
    FakeXhr.instances.push(this);
  }

  open() {}
  send() {}

  addEventListener(type: string, fn: () => void) {
    this.handlers[type] = fn;
  }

  abort() {
    this.aborted = true;
    this.handlers.abort?.();
  }

  emitProgress(loaded: number, total: number) {
    this.progress?.({ lengthComputable: true, loaded, total });
  }

  respond(status: number, body = '') {
    this.status = status;
    this.responseText = body;
    this.handlers.load?.();
  }

  fail() {
    this.handlers.error?.();
  }
}

const TOO_LARGE = JSON.stringify({
  detail: { code: 'file_storage.too_large', message: 'exceeds the 25 MB limit' },
});

function file(name = 'huge.zip') {
  return new File(['payload'], name, { type: 'application/zip' });
}

beforeEach(() => {
  FakeXhr.instances = [];
  vi.stubGlobal('XMLHttpRequest', FakeXhr);
});

describe('parseFailureReason', () => {
  test("reads the API's own explanation out of the error body", () => {
    expect(parseFailureReason(TOO_LARGE)).toBe('exceeds the 25 MB limit');
  });

  test('accepts a plain-string detail', () => {
    expect(parseFailureReason(JSON.stringify({ detail: 'Not authenticated' }))).toBe(
      'Not authenticated',
    );
  });

  test.each([
    ['a proxy error page', '<html><body>502 Bad Gateway</body></html>'],
    ['an empty body', ''],
    ['JSON with no detail', '{"ok":false}'],
    ['a detail with no message', '{"detail":{"code":"x"}}'],
  ])('has nothing to say about %s', (_label, body) => {
    expect(parseFailureReason(body)).toBeUndefined();
  });
});

describe('useUploadQueue', () => {
  test('tracks byte progress while a file is in flight', async () => {
    const { result } = renderHook(() => useUploadQueue());
    act(() => {
      void result.current.start([file()]);
    });

    act(() => FakeXhr.instances[0].emitProgress(32, 128));

    expect(result.current.jobs[0]).toMatchObject({ percent: 25, status: 'uploading' });
    expect(result.current.busy).toBe(true);
  });

  test('a rejected upload keeps the reason the server gave', async () => {
    const { result } = renderHook(() => useUploadQueue());
    let batch!: Promise<{ uploaded: number; failed: string[] }>;
    act(() => {
      batch = result.current.start([file()]);
    });

    await act(async () => {
      FakeXhr.instances[0].respond(413, TOO_LARGE);
      await batch;
    });

    expect(result.current.jobs).toHaveLength(1);
    expect(result.current.jobs[0]).toMatchObject({
      status: 'error',
      reason: 'exceeds the 25 MB limit',
    });
    expect(await batch).toEqual({ uploaded: 0, failed: ['huge.zip'] });
  });

  test('a dropped connection fails the row without inventing a reason', async () => {
    const { result } = renderHook(() => useUploadQueue());
    let batch!: Promise<{ uploaded: number; failed: string[] }>;
    act(() => {
      batch = result.current.start([file()]);
    });

    await act(async () => {
      FakeXhr.instances[0].fail();
      await batch;
    });

    expect(result.current.jobs[0].status).toBe('error');
    expect(result.current.jobs[0].reason).toBeUndefined();
  });

  test('a finished upload leaves no row behind', async () => {
    const { result } = renderHook(() => useUploadQueue());
    let batch!: Promise<{ uploaded: number; failed: string[] }>;
    act(() => {
      batch = result.current.start([file('logo.png')]);
    });

    await act(async () => {
      FakeXhr.instances[0].respond(201, '{}');
      await batch;
    });

    expect(result.current.jobs).toEqual([]);
    expect(await batch).toEqual({ uploaded: 1, failed: [] });
  });

  test('cancelling aborts the request and drops the row', async () => {
    const { result } = renderHook(() => useUploadQueue());
    let batch!: Promise<{ uploaded: number; failed: string[] }>;
    act(() => {
      batch = result.current.start([file()]);
    });
    const id = result.current.jobs[0].id;

    await act(async () => {
      result.current.cancel(id);
      await batch;
    });

    expect(FakeXhr.instances[0].aborted).toBe(true);
    expect(result.current.jobs).toEqual([]);
    // A cancel is the user's own doing: it must not surface as a failure.
    expect(await batch).toEqual({ uploaded: 0, failed: [] });
  });

  test('retrying re-sends the same file without asking for it again', async () => {
    const { result } = renderHook(() => useUploadQueue());
    let batch!: Promise<{ uploaded: number; failed: string[] }>;
    act(() => {
      batch = result.current.start([file()]);
    });
    await act(async () => {
      FakeXhr.instances[0].respond(502, '');
      await batch;
    });
    const id = result.current.jobs[0].id;

    let retried!: Promise<boolean>;
    act(() => {
      retried = result.current.retry(id);
    });
    expect(result.current.jobs[0]).toMatchObject({ status: 'uploading', percent: 0 });

    await act(async () => {
      FakeXhr.instances[1].respond(201, '{}');
      await retried;
    });

    expect(FakeXhr.instances).toHaveLength(2);
    expect(result.current.jobs).toEqual([]);
  });

  test('a row dismissed by hand cannot be retried', async () => {
    const { result } = renderHook(() => useUploadQueue());
    let batch!: Promise<{ uploaded: number; failed: string[] }>;
    act(() => {
      batch = result.current.start([file()]);
    });
    await act(async () => {
      FakeXhr.instances[0].respond(500, '');
      await batch;
    });
    const id = result.current.jobs[0].id;

    act(() => {
      result.current.dismiss(id);
    });

    await expect(result.current.retry(id)).resolves.toBe(false);
    expect(FakeXhr.instances).toHaveLength(1);
  });
});
