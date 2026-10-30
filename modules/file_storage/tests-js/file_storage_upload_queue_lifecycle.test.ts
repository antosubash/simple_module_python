import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

const { maps, findSession, runResumable, reload, discardSession } = vi.hoisted(() => ({
  maps: [] as Map<string, File>[],
  findSession: vi.fn(),
  runResumable: vi.fn(),
  reload: vi.fn(),
  discardSession: vi.fn(),
}));

vi.mock('react', async (importOriginal) => {
  const react = await importOriginal<typeof import('react')>();
  return {
    ...react,
    useRef: <T>(initial: T) => {
      const ref = react.useRef(initial);
      if (initial instanceof Map && !maps.includes(ref.current as Map<string, File>)) {
        maps.push(ref.current as Map<string, File>);
      }
      return ref;
    },
  };
});
vi.mock('@inertiajs/react', () => ({ router: { reload } }));
vi.mock('../file_storage/pages/resumable-upload', () => ({
  findSession,
  runResumable,
  discardSession,
}));

import type { RemoteSession } from '../file_storage/pages/resumable-upload';
import { useUploadQueue } from '../file_storage/pages/upload-queue';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

const file = () => new File(['payload'], 'example.txt');

beforeEach(() => {
  maps.length = 0;
  findSession.mockReset().mockResolvedValue(null);
  runResumable.mockReset().mockResolvedValue(undefined);
  reload.mockReset();
  discardSession.mockReset().mockResolvedValue(undefined);
});

const sessionDefaults = {
  total_size: 7,
  part_size: 2,
  total_parts: 4,
  status: 'active' as const,
};
const sessions: (RemoteSession | null)[] = [
  null,
  { ...sessionDefaults, id: 'empty', parts: [] },
  { ...sessionDefaults, id: 'partial', parts: [{ no: 1, etag: 'etag', size: 2 }] },
];

test.each(sessions)('cancel during session lookup starts no transport (%j)', async (session) => {
  const lookup = deferred<RemoteSession | null>();
  findSession.mockReturnValue(lookup.promise);
  const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: 1 }));
  let batch!: ReturnType<typeof result.current.start>;
  act(() => {
    batch = result.current.start([file()]);
  });
  expect(findSession).toHaveBeenCalledOnce();
  act(() => result.current.cancel(result.current.jobs[0].id));
  await act(async () => {
    lookup.resolve(session);
    expect(await batch).toEqual({ uploaded: 0, failed: [] });
  });
  expect(runResumable).not.toHaveBeenCalled();
  expect(result.current.jobs).toEqual([]);
  expect(maps.every((map) => map.size === 0)).toBe(true);
});

test('cancel during retry session lookup starts no transport', async () => {
  runResumable.mockRejectedValueOnce(new Error('connection lost'));
  const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: 1 }));
  await act(async () => {
    await result.current.start([file()]);
  });
  const lookup = deferred<RemoteSession | null>();
  findSession.mockReturnValue(lookup.promise);
  let retry!: Promise<boolean>;
  act(() => {
    retry = result.current.retry(result.current.jobs[0].id);
  });
  act(() => result.current.cancel(result.current.jobs[0].id));
  await act(async () => {
    lookup.resolve(null);
    expect(await retry).toBe(false);
  });
  expect(runResumable).toHaveBeenCalledOnce();
  expect(result.current.jobs).toEqual([]);
});

test('successful batch releases files when the reload clears completed rows', async () => {
  const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: 1 }));
  await act(async () => {
    expect(await result.current.start([file(), file()])).toEqual({ uploaded: 2, failed: [] });
  });
  const files = maps[0];
  expect(files.size).toBe(2);
  expect(result.current.jobs.every((job) => job.status === 'done')).toBe(true);
  act(() => reload.mock.calls[0][0].onFinish());
  expect(result.current.jobs).toEqual([]);
  expect(files.size).toBe(0);
});

test('batch cleanup keeps failed and concurrently uploading files for retry', async () => {
  runResumable.mockRejectedValueOnce(new Error('connection lost'));
  const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: 1 }));
  await act(async () => {
    await result.current.start([file(), file()]);
  });
  const pending = deferred<void>();
  runResumable.mockReturnValue(pending.promise);
  let batch!: ReturnType<typeof result.current.start>;
  await act(async () => {
    batch = result.current.start([file()]);
  });
  act(() => reload.mock.calls[0][0].onFinish());
  expect(result.current.jobs.map((job) => job.status)).toEqual(['error', 'uploading']);
  expect([...maps[0].keys()]).toEqual(result.current.jobs.map((job) => job.id));
  await act(async () => {
    pending.resolve();
    await batch;
  });
  act(() => reload.mock.calls[1][0].onFinish());
  expect(maps[0].size).toBe(1);
  await act(async () => {
    runResumable.mockResolvedValue(undefined);
    expect(await result.current.retry(result.current.jobs[0].id)).toBe(true);
  });
  act(() => reload.mock.calls[2][0].onFinish());
  expect(maps[0].size).toBe(0);
});

test('cancel while start-over discards the old session starts no transport', async () => {
  const partial = sessions[2];
  runResumable.mockRejectedValueOnce(new Error('connection lost'));
  findSession.mockResolvedValue(partial);
  const { result } = renderHook(() => useUploadQueue({ directThresholdBytes: 1 }));
  await act(async () => {
    await result.current.start([file()]);
  });
  expect(result.current.jobs[0].status).toBe('resumable');
  const discard = deferred<void>();
  discardSession.mockReturnValue(discard.promise);
  let restarted!: Promise<boolean>;
  act(() => {
    restarted = result.current.startOver(result.current.jobs[0].id);
  });
  act(() => result.current.cancel(result.current.jobs[0].id));
  await act(async () => {
    discard.resolve();
    expect(await restarted).toBe(false);
  });
  expect(runResumable).not.toHaveBeenCalled();
});
