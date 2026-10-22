import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

const state = vi.hoisted(() => ({ props: {} as Record<string, unknown> }));
const visit = vi.hoisted(() => vi.fn());

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { reload: vi.fn(), get: vi.fn(), visit },
  usePage: () => ({ props: state.props }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import type { TaskDetail } from '../background_tasks/pages/constants';
import Detail from '../background_tasks/pages/Detail';
import { stubFetch } from './stub-fetch';

const rd = keys.background_tasks.retry_dialog;

function execution(over: Partial<TaskDetail> = {}): TaskDetail {
  return {
    id: 'e1',
    celery_task_id: 'c1',
    task_name: 'demo.task',
    status: 'failed',
    queue: 'default',
    tenant_id: null,
    args: [1, 'two'],
    kwargs: { flag: true },
    result: null,
    traceback: 'Traceback (most recent call last)',
    exception_type: 'ValueError',
    worker: 'w1',
    retries: 2,
    retried_from_id: null,
    owner_user_id: null,
    progress_current: null,
    progress_total: null,
    progress_message: null,
    progress_phase: null,
    queued_at: '2026-01-01T00:00:00Z',
    started_at: '2026-01-01T00:00:01Z',
    finished_at: '2026-01-01T00:00:02Z',
    heartbeat_at: null,
    ...over,
  };
}

function setProps(over: Partial<TaskDetail> = {}, permissions = ['background_tasks.manage']) {
  state.props = { execution: execution(over), max_retries: 3, auth: { permissions } };
}

describe('background_tasks Detail page', () => {
  beforeEach(() => setProps());
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('renders the task and its traceback', () => {
    render(<Detail {...(state.props as unknown as ComponentProps<typeof Detail>)} />);
    expect(screen.getAllByText('demo.task').length).toBeGreaterThan(0);
    expect(screen.getByText('Traceback (most recent call last)')).toBeInTheDocument();
  });

  it('shows a progress bar only when the task reported progress', () => {
    const { unmount } = render(<Detail />);
    expect(screen.queryByTestId('task-progress')).toBeNull();
    unmount();

    setProps({ progress_current: 3, progress_total: 10, progress_message: 'copying rows' });
    render(<Detail />);
    expect(screen.getByTestId('task-progress')).toBeInTheDocument();
    expect(screen.getByText('copying rows')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '30');
  });

  it('offers no retry to a viewer without the manage permission', () => {
    setProps({}, []);
    render(<Detail {...(state.props as unknown as ComponentProps<typeof Detail>)} />);
    expect(
      screen.queryByRole('button', { name: keys.background_tasks.detail.retry_button }),
    ).toBeNull();
  });

  it('offers no retry for a task that already succeeded', () => {
    setProps({ status: 'success' });
    render(<Detail {...(state.props as unknown as ComponentProps<typeof Detail>)} />);
    expect(
      screen.queryByRole('button', { name: keys.background_tasks.detail.retry_button }),
    ).toBeNull();
  });

  it('confirms with the payload and retry count before re-enqueueing', async () => {
    const fetchMock = stubFetch(200, { id: 'e2' });
    render(<Detail {...(state.props as unknown as ComponentProps<typeof Detail>)} />);
    fireEvent.click(
      screen.getAllByRole('button', { name: keys.background_tasks.detail.retry_button })[0],
    );

    expect(await screen.findByText(rd.args_label, { exact: false })).toBeInTheDocument();
    expect(screen.getByText(rd.kwargs_label, { exact: false })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not call the API when the confirm is cancelled', async () => {
    const fetchMock = stubFetch(200, { id: 'e2' });
    render(<Detail {...(state.props as unknown as ComponentProps<typeof Detail>)} />);
    fireEvent.click(
      screen.getAllByRole('button', { name: keys.background_tasks.detail.retry_button })[0],
    );
    fireEvent.click(await screen.findByRole('button', { name: rd.cancel }));

    await waitFor(() => expect(screen.queryByText(rd.description, { exact: false })).toBeNull());
    expect(fetchMock).not.toHaveBeenCalled();
    expect(visit).not.toHaveBeenCalled();
  });

  it('retries on confirm, toasts and navigates to the new execution', async () => {
    const fetchMock = stubFetch(200, { id: 'e2' });
    render(<Detail {...(state.props as unknown as ComponentProps<typeof Detail>)} />);
    fireEvent.click(
      screen.getAllByRole('button', { name: keys.background_tasks.detail.retry_button })[0],
    );
    fireEvent.click(await screen.findByRole('button', { name: rd.confirm }));

    await waitFor(() => expect(visit).toHaveBeenCalledWith('/admin/background-tasks/e2'));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/background_tasks/admin/executions/e1/retry',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('shows the server message and stays put when the retry fails', async () => {
    stubFetch(409, { detail: 'Already retried' });
    render(<Detail {...(state.props as unknown as ComponentProps<typeof Detail>)} />);
    fireEvent.click(
      screen.getAllByRole('button', { name: keys.background_tasks.detail.retry_button })[0],
    );
    fireEvent.click(await screen.findByRole('button', { name: rd.confirm }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Already retried'));
    expect(visit).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });
});
