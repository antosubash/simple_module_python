import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

const state = vi.hoisted(() => ({ props: {} as Record<string, unknown> }));
const reload = vi.hoisted(() => vi.fn());
const get = vi.hoisted(() => vi.fn());

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { reload, get, visit: vi.fn() },
  usePage: () => ({ props: state.props }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import Outbox from '../background_tasks/pages/Outbox';
import type { OutboxMessage } from '../background_tasks/pages/outbox';

const ob = keys.background_tasks.outbox;

function message(over: Partial<OutboxMessage> = {}): OutboxMessage {
  return {
    id: 'm1',
    event_key: 'orders.contracts.events.OrderPlaced',
    handler_name: 'billing.handlers.charge',
    payload: {},
    tenant_id: null,
    status: 'dead',
    attempts: 5,
    next_attempt_at: '2026-01-01T00:00:00Z',
    locked_until: null,
    last_error: 'Boom\nTraceback...',
    created_at: '2026-01-01T00:00:00Z',
    delivered_at: null,
    ...over,
  };
}

function setProps(over: Record<string, unknown> = {}, permissions = ['background_tasks.manage']) {
  state.props = {
    messages: [message()],
    counts: { pending: 2, running: 0, dead: 1 },
    pagination: { page: 1, per_page: 20, total: 1 },
    filters: { status: '' },
    auth: { permissions },
    ...over,
  };
}

function stubFetch(status: number, body: unknown = {}) {
  const fetchMock = vi.fn(
    async () => new Response(status === 204 ? null : JSON.stringify(body), { status }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('background_tasks Outbox page', () => {
  beforeEach(() => setProps());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  it('lists messages with the short event name and first error line', () => {
    render(<Outbox />);
    expect(screen.getByText('OrderPlaced')).toBeInTheDocument();
    expect(screen.getByText('billing.handlers.charge')).toBeInTheDocument();
    expect(screen.getByText('Boom')).toBeInTheDocument();
  });

  it('shows the empty state', () => {
    setProps({ messages: [], pagination: { page: 1, per_page: 20, total: 0 } });
    render(<Outbox />);
    expect(screen.getByText(ob.empty_title)).toBeInTheDocument();
  });

  it('hides row actions without the manage permission', () => {
    setProps({}, []);
    render(<Outbox />);
    expect(screen.queryByRole('button', { name: ob.retry })).toBeNull();
    expect(screen.queryByRole('button', { name: ob.discard })).toBeNull();
  });

  it('offers no action on a running message and no retry on a pending one', () => {
    setProps({
      messages: [message({ id: 'a', status: 'running' }), message({ id: 'b', status: 'pending' })],
    });
    render(<Outbox />);
    expect(screen.queryByRole('button', { name: ob.retry })).toBeNull();
    expect(screen.getAllByRole('button', { name: ob.discard })).toHaveLength(1);
  });

  it('replays a dead message with a POST, toasts and reloads the list', async () => {
    const fetchMock = stubFetch(200, { id: 'm1', status: 'pending' });
    render(<Outbox />);
    fireEvent.click(screen.getByRole('button', { name: ob.retry }));

    await waitFor(() => expect(reload).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/background_tasks/admin/outbox/m1/retry',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(toast.success).toHaveBeenCalledWith(ob.retried);
    expect(reload).toHaveBeenCalledWith({ only: ['messages', 'counts', 'pagination'] });
  });

  it('shows the translated conflict and still reloads when replay is refused', async () => {
    stubFetch(409, { detail: 'English server text' });
    render(<Outbox />);
    fireEvent.click(screen.getByRole('button', { name: ob.retry }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(ob.conflict));
    expect(toast.success).not.toHaveBeenCalled();
    expect(reload).toHaveBeenCalled();
  });

  it('reports a vanished row on 404 and a generic failure otherwise', async () => {
    stubFetch(404);
    const { unmount } = render(<Outbox />);
    fireEvent.click(screen.getByRole('button', { name: ob.retry }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(ob.gone));
    unmount();

    stubFetch(500);
    render(<Outbox />);
    fireEvent.click(screen.getByRole('button', { name: ob.retry }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(ob.retry_failed));
  });

  it('asks before discarding and calls nothing when the operator declines', () => {
    const fetchMock = stubFetch(204);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<Outbox />);
    fireEvent.click(screen.getByRole('button', { name: ob.discard }));

    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
  });

  it('discards with a DELETE once confirmed', async () => {
    const fetchMock = stubFetch(204);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<Outbox />);
    fireEvent.click(screen.getByRole('button', { name: ob.discard }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(ob.discarded));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/background_tasks/admin/outbox/m1',
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(reload).toHaveBeenCalled();
  });

  it('toasts a discard failure', async () => {
    stubFetch(500);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<Outbox />);
    fireEvent.click(screen.getByRole('button', { name: ob.discard }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(ob.discard_failed));
  });

  it('filters by status through a page-1 visit', () => {
    render(<Outbox />);
    fireEvent.click(screen.getByRole('button', { name: new RegExp(ob.status_dead) }));
    expect(get).toHaveBeenCalledWith(
      '/admin/background-tasks/outbox',
      { status: 'dead' },
      expect.objectContaining({ preserveState: true }),
    );
  });
});
