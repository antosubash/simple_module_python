import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';

vi.mock('@inertiajs/react', () => ({
  router: {
    reload: vi.fn((options?: { onFinish?: () => void }) => options?.onFinish?.()),
  },
}));

vi.mock('../file_storage/pages/constants', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../file_storage/pages/constants')>()),
  UPLOAD_CONCURRENCY: 1,
}));

import { useUploadQueue } from '../file_storage/pages/upload-queue';

class PendingXhr {
  static instances: PendingXhr[] = [];
  status = 201;
  responseText = '{}';
  upload = { addEventListener: vi.fn() };
  private handlers = new Map<string, () => void>();

  constructor() {
    PendingXhr.instances.push(this);
  }

  open() {}
  send() {}

  addEventListener(type: string, callback: () => void) {
    this.handlers.set(type, callback);
  }

  finish() {
    this.handlers.get('load')?.();
  }
}

afterEach(() => vi.unstubAllGlobals());

test('cancelling a queued upload prevents its transport from starting', async () => {
  PendingXhr.instances = [];
  vi.stubGlobal('XMLHttpRequest', PendingXhr);
  const { result } = renderHook(() => useUploadQueue());
  let batch!: ReturnType<typeof result.current.start>;
  act(() => {
    batch = result.current.start([
      new File(['first'], 'first.txt'),
      new File(['second'], 'second.txt'),
    ]);
  });

  expect(result.current.jobs).toHaveLength(2);
  expect(PendingXhr.instances).toHaveLength(1);
  const cancelledId = result.current.jobs[1].id;
  act(() => result.current.cancel(cancelledId));
  expect(result.current.jobs.map((job) => job.name)).toEqual(['first.txt']);

  await act(async () => {
    PendingXhr.instances[0].finish();
    // Let the worker claim its next job before checking the transport count.
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(PendingXhr.instances).toHaveLength(1);
  await act(async () => {
    expect(await batch).toEqual({ uploaded: 1, failed: [] });
  });
  expect(result.current.jobs).toEqual([]);
  expect(result.current.busy).toBe(false);
});
