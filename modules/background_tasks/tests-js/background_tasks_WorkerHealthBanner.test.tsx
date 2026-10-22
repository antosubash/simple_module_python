import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

vi.mock('@inertiajs/react', () => ({
  Link: ({ children }: { children: unknown }) => <a href="/x">{children as string}</a>,
}));

import { WorkerHealthBanner } from '../background_tasks/pages/components/WorkerHealthBanner';
import { requestsOf, stubFetch } from './stub-fetch';

const snapshot = (reachable: boolean) => ({
  broker_reachable: reachable,
  polled_at: '2026-01-01T00:00:00Z',
  workers: [],
  error: null,
});

describe('WorkerHealthBanner', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('does not call the API without a backlog', () => {
    const fetchMock = stubFetch(200, snapshot(true));
    render(<WorkerHealthBanner backlog={0} />);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('warns when the broker is unreachable', async () => {
    const fetchMock = stubFetch(200, snapshot(false));
    render(<WorkerHealthBanner backlog={3} />);
    expect(
      await screen.findByText(keys.background_tasks.worker_health.broker_unreachable_title),
    ).toBeInTheDocument();
    expect(requestsOf(fetchMock)[0]).toEqual({
      url: '/api/background_tasks/admin/workers',
      method: 'GET',
    });
  });

  it('aborts the in-flight request on unmount', async () => {
    let signal: AbortSignal | undefined;
    const fetchMock = vi.fn(async (req: Request) => {
      signal = req.signal;
      return new Promise<Response>(() => {});
    });
    vi.stubGlobal('fetch', fetchMock);
    const { unmount } = render(<WorkerHealthBanner backlog={3} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(signal?.aborted).toBe(false);
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it('stays silent when the API call fails', async () => {
    const fetchMock = stubFetch(403, { detail: 'nope' });
    const { container } = render(<WorkerHealthBanner backlog={3} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
