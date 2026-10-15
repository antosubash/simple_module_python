import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import {
  discardOutboxMessage,
  retryOutboxMessage,
  shortName,
} from '../background_tasks/pages/outbox';

function stubFetch(status: number, body: unknown = {}) {
  const fetchMock = vi.fn(
    async () => new Response(status === 204 ? null : JSON.stringify(body), { status }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('outbox actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('retries with a POST to the row', async () => {
    const fetchMock = stubFetch(200, { id: 'm1', status: 'pending' });
    expect(await retryOutboxMessage('m1')).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/background_tasks/admin/outbox/m1/retry',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('discards with a DELETE and accepts 204', async () => {
    const fetchMock = stubFetch(204);
    expect(await discardOutboxMessage('m1')).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/background_tasks/admin/outbox/m1',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('surfaces the server detail on a conflict', async () => {
    stubFetch(409, { detail: 'Only dead messages can be retried' });
    expect(await retryOutboxMessage('m1')).toBe(false);
    expect(toast.error).toHaveBeenCalledWith('Only dead messages can be retried');
  });
});

describe('shortName', () => {
  it('keeps the class name of a dotted event key', () => {
    expect(shortName('orders.contracts.events.OrderPlaced')).toBe('OrderPlaced');
    expect(shortName('Plain')).toBe('Plain');
  });
});
