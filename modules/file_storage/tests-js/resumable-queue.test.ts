import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

vi.mock('@inertiajs/react', () => ({
  router: {
    reload: vi.fn((options?: { onFinish?: () => void }) => options?.onFinish?.()),
  },
}));

const runResumable = vi.fn();
const findSession = vi.fn();
const discardSession = vi.fn();
vi.mock('../file_storage/pages/resumable-upload', () => ({
  runResumable: (...args: unknown[]) => runResumable(...args),
  findSession: (...args: unknown[]) => findSession(...args),
  discardSession: (...args: unknown[]) => discardSession(...args),
}));

import { UploadAbortedError, UploadFailedError } from '../file_storage/pages/upload-errors';
import { useUploadQueue } from '../file_storage/pages/upload-queue';

const THRESHOLD = 100;

function file(size: number, name = 'movie.bin') {
  return new File([new Uint8Array(size)], name, { lastModified: 1 });
}

class NeverXhr {
  static opened = 0;
  upload = { addEventListener() {} };
  open() {
    NeverXhr.opened += 1;
  }
  addEventListener() {}
  send() {}
  abort() {}
}

beforeEach(() => {
  runResumable.mockReset().mockResolvedValue(undefined);
  findSession.mockReset().mockResolvedValue(null);
  discardSession.mockReset().mockResolvedValue(undefined);
  NeverXhr.opened = 0;
  vi.stubGlobal('XMLHttpRequest', NeverXhr);
});

afterEach(() => vi.unstubAllGlobals());

describe('the resumable path in useUploadQueue', () => {
  test('files at or under the threshold still use the one-shot form post', async () => {
    const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: THRESHOLD }));
    act(() => {
      void result.current.start([file(THRESHOLD)]);
    });
    await waitFor(() => expect(NeverXhr.opened).toBe(1));
    expect(runResumable).not.toHaveBeenCalled();
  });

  test('no threshold (backend cannot do it) never uses sessions', async () => {
    const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: null }));
    act(() => {
      void result.current.start([file(10_000)]);
    });
    await waitFor(() => expect(NeverXhr.opened).toBe(1));
    expect(runResumable).not.toHaveBeenCalled();
  });

  test('a file over the threshold uploads in parts and reports progress', async () => {
    runResumable.mockImplementation(async (_file, options) => {
      options.onProgress(50, 200);
    });
    const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: THRESHOLD }));
    let batch!: Promise<{ uploaded: number; failed: string[] }>;
    act(() => {
      batch = result.current.start([file(200)]);
    });
    await act(async () => {
      expect(await batch).toEqual({ uploaded: 1, failed: [] });
    });
    expect(NeverXhr.opened).toBe(0);
    expect(result.current.jobs).toEqual([]);
  });

  test('a failed part upload keeps the server reason and retry resumes without asking', async () => {
    runResumable.mockRejectedValueOnce(new UploadFailedError(413, 'over the quota'));
    const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: THRESHOLD }));
    let batch!: Promise<{ uploaded: number; failed: string[] }>;
    act(() => {
      batch = result.current.start([file(200)]);
    });
    await act(async () => {
      expect((await batch).failed).toEqual(['movie.bin']);
    });
    expect(result.current.jobs[0]).toMatchObject({ status: 'error', reason: 'over the quota' });

    // The stored session has parts, yet a retry must not stop to prompt.
    findSession.mockResolvedValue({ id: 's', parts: [{ no: 1, etag: 'e', size: 10 }] });
    await act(async () => {
      expect(await result.current.retry(result.current.jobs[0].id)).toBe(true);
    });
    expect(runResumable).toHaveBeenLastCalledWith(expect.any(File), expect.anything(), {
      id: 's',
      parts: [{ no: 1, etag: 'e', size: 10 }],
    });
  });

  test('re-selecting a partly sent file offers to resume instead of sending', async () => {
    findSession.mockResolvedValue({
      id: 'sess',
      parts: [{ no: 1, etag: 'e', size: 50 }],
    });
    const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: THRESHOLD }));
    await act(async () => {
      await result.current.start([file(200)]);
    });

    expect(runResumable).not.toHaveBeenCalled();
    expect(result.current.jobs[0]).toMatchObject({ status: 'resumable', percent: 25 });
    expect(result.current.busy).toBe(false);

    await act(async () => {
      expect(await result.current.resume(result.current.jobs[0].id)).toBe(true);
    });
    expect(runResumable.mock.calls[0][2]).toMatchObject({ id: 'sess' });
  });

  test('start over discards the stored session and begins a fresh one', async () => {
    findSession.mockResolvedValue({ id: 'sess', parts: [{ no: 1, etag: 'e', size: 50 }] });
    const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: THRESHOLD }));
    await act(async () => {
      await result.current.start([file(200)]);
    });

    await act(async () => {
      await result.current.startOver(result.current.jobs[0].id);
    });

    expect(discardSession).toHaveBeenCalledWith(expect.any(File), 'sess');
    expect(runResumable.mock.calls[0][2]).toBeNull();
  });

  test('a session with no parts yet just continues, no prompt', async () => {
    findSession.mockResolvedValue({ id: 'sess', parts: [] });
    const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: THRESHOLD }));
    await act(async () => {
      await result.current.start([file(200)]);
    });
    expect(runResumable.mock.calls[0][2]).toMatchObject({ id: 'sess' });
  });

  test('cancelling aborts the parts and frees the server session', async () => {
    let signal!: AbortSignal;
    runResumable.mockImplementation(
      (_f: File, options: { signal: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          signal = options.signal;
          signal.addEventListener('abort', () => reject(new UploadAbortedError()));
        }),
    );
    window.localStorage.setItem(`file_storage.upload.movie.bin:200:1`, 'sess');
    const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: THRESHOLD }));
    let batch!: Promise<{ uploaded: number; failed: string[] }>;
    act(() => {
      batch = result.current.start([file(200)]);
    });
    await waitFor(() => expect(runResumable).toHaveBeenCalled());

    await act(async () => {
      result.current.cancel(result.current.jobs[0].id);
      expect(await batch).toEqual({ uploaded: 0, failed: [] });
    });

    expect(signal.aborted).toBe(true);
    expect(discardSession).toHaveBeenCalledWith(expect.any(File), 'sess');
    expect(result.current.jobs).toEqual([]);
  });
});
