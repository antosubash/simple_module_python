import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  usePage: () => ({ props: { auth: { permissions: [] } } }),
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import type { WorkerSnapshot } from '../background_tasks/pages/constants';
import Workers from '../background_tasks/pages/Workers';

const w = keys.background_tasks.workers;
const base = { broker_url_redacted: 'redis://localhost:6379/0', queues: ['default'], routes: [] };
const snapshot: WorkerSnapshot = {
  broker_reachable: true,
  polled_at: '2026-01-01T12:00:00Z',
  error: null,
  workers: [
    {
      hostname: 'celery@host-a',
      online: true,
      queues: ['default'],
      active_task_count: 0,
      pool_size: 4,
      total_processed: 10,
      software: null,
      uptime_seconds: 60,
    },
  ],
};

describe('background_tasks Workers page', () => {
  it('holds the fleet space with a busy skeleton until the deferred snapshot lands', () => {
    const { rerender } = render(<Workers {...base} />);
    expect(screen.getByRole('status', { name: w.checking_label })).toHaveAttribute(
      'aria-busy',
      'true',
    );
    expect(screen.getByText(w.checking)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: w.refresh })).toBeDisabled();

    rerender(<Workers {...base} snapshot={snapshot} />);
    expect(screen.queryByRole('status', { name: w.checking_label })).toBeNull();
    expect(screen.getByText('celery@host-a')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: w.refresh })).toBeEnabled();
  });
});
