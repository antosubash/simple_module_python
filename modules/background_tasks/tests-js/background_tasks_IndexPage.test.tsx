import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

const state = vi.hoisted(() => ({ props: {} as Record<string, unknown> }));
const reload = vi.hoisted(() => vi.fn());

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { reload, get: vi.fn(), visit: vi.fn() },
  usePage: () => ({ props: state.props }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import Index from '../background_tasks/pages/Index';
import type { Execution } from '../background_tasks/pages/retry';

const rd = keys.background_tasks.retry_dialog;
const ra = keys.background_tasks.retry_all_dialog;
const RELOAD = { only: ['executions', 'pagination', 'status_counts', 'queues'] };

function execution(over: Partial<Execution> = {}): Execution {
  return {
    id: 'e1',
    celery_task_id: 'c1',
    task_name: 'demo.task',
    status: 'failed',
    queue: 'default',
    tenant_id: null,
    args: [],
    kwargs: {},
    retries: 0,
    worker: null,
    queued_at: '2026-01-01T00:00:00Z',
    started_at: null,
    finished_at: null,
    exception_type: 'ValueError',
    retried_from_id: null,
    ...over,
  };
}

function setProps(over: Record<string, unknown> = {}, permissions = ['background_tasks.manage']) {
  state.props = {
    executions: [execution()],
    pagination: { page: 1, per_page: 20, total: 1 },
    filters: { status: '', task_name: '', queue: '', tenant: '' },
    status_counts: { failed: 1 },
    queues: ['default'],
    tenant_ids: [],
    platform_tenant_value: '__platform__',
    worker_presence: null,
    has_executions: true,
    auth: { permissions },
    ...over,
  };
}

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('background_tasks Index page', () => {
  beforeEach(() => setProps());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('lists executions and offers retry controls to managers only', () => {
    render(<Index />);
    expect(screen.getByText('demo.task')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: keys.background_tasks.table.retry }),
    ).toBeInTheDocument();
    cleanup();

    setProps({}, []);
    render(<Index />);
    expect(screen.queryByRole('button', { name: keys.background_tasks.table.retry })).toBeNull();
    expect(
      screen.queryByRole('button', { name: keys.background_tasks.index.retry_all_button }),
    ).toBeNull();
  });

  it('retries one row only after the confirm, then reloads the list and strip', async () => {
    const fetchMock = stubFetch(200, { id: 'e2' });
    render(<Index />);
    fireEvent.click(screen.getByRole('button', { name: keys.background_tasks.table.retry }));
    expect(await screen.findByText(rd.no_args)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: rd.confirm }));
    await waitFor(() => expect(reload).toHaveBeenCalledWith(RELOAD));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/background_tasks/admin/executions/e1/retry',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('does nothing when the single retry is cancelled', async () => {
    const fetchMock = stubFetch(200, { id: 'e2' });
    render(<Index />);
    fireEvent.click(screen.getByRole('button', { name: keys.background_tasks.table.retry }));
    fireEvent.click(await screen.findByRole('button', { name: rd.cancel }));
    await waitFor(() => expect(screen.queryByText(rd.no_args)).toBeNull());
    expect(fetchMock).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
  });

  it('toasts the failure and skips the reload when a single retry errors', async () => {
    stubFetch(500, { detail: 'Broker down' });
    render(<Index />);
    fireEvent.click(screen.getByRole('button', { name: keys.background_tasks.table.retry }));
    fireEvent.click(await screen.findByRole('button', { name: rd.confirm }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Broker down'));
    expect(reload).not.toHaveBeenCalled();
  });

  it('retry-all states its scope, then posts with the active filters', async () => {
    setProps({ filters: { status: 'failed', task_name: 'demo', queue: 'default', tenant: '' } });
    const fetchMock = stubFetch(200, { queued: 4, remaining: 0 });
    render(<Index />);
    fireEvent.click(
      screen.getByRole('button', { name: keys.background_tasks.index.retry_all_button }),
    );
    expect(await screen.findByText(ra.description)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: ra.confirm }));
    await waitFor(() => expect(reload).toHaveBeenCalledWith(RELOAD));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/background_tasks/admin/executions/retry-failed?status=failed&q=demo&queue=default',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('retry-all mentions the backlog when the server capped the pass', async () => {
    stubFetch(200, { queued: 2, remaining: 7 });
    render(<Index />);
    fireEvent.click(
      screen.getByRole('button', { name: keys.background_tasks.index.retry_all_button }),
    );
    fireEvent.click(await screen.findByRole('button', { name: ra.confirm }));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith(
      keys.background_tasks.toasts.bulk_retried,
      expect.objectContaining({ description: keys.background_tasks.toasts.bulk_remaining }),
    );
  });

  it('retry-all does not call the API when cancelled', async () => {
    const fetchMock = stubFetch(200, { queued: 1, remaining: 0 });
    render(<Index />);
    fireEvent.click(
      screen.getByRole('button', { name: keys.background_tasks.index.retry_all_button }),
    );
    fireEvent.click(await screen.findByRole('button', { name: ra.cancel }));
    await waitFor(() => expect(screen.queryByText(ra.description)).toBeNull());
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('retry-all toasts an error and does not reload on failure', async () => {
    stubFetch(403, { detail: 'Forbidden' });
    render(<Index />);
    fireEvent.click(
      screen.getByRole('button', { name: keys.background_tasks.index.retry_all_button }),
    );
    fireEvent.click(await screen.findByRole('button', { name: ra.confirm }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Forbidden'));
    expect(reload).not.toHaveBeenCalled();
  });
});
