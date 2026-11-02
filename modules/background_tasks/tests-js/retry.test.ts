import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { retryExecution } from '../background_tasks/pages/retry';

const row = { id: 'abc', task_name: 'demo.task' };

function stubFetch() {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: 'new' }), { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('retryExecution', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('sends one POST for a burst of clicks on the same row', async () => {
    const fetchMock = stubFetch();
    const results = await Promise.all([1, 2, 3, 4, 5].map(() => retryExecution(row)));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(results.every((r) => r?.id === 'new')).toBe(true);
  });

  it('allows retrying the same row again once the first request settled', async () => {
    const fetchMock = stubFetch();
    await retryExecution(row);
    await retryExecution(row);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
