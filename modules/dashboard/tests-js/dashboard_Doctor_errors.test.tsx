import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, expect, test, vi } from 'vitest';
import Doctor from '../dashboard/pages/Doctor';

configureI18n({ locale: 'en', messages: {} });
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  router: { post },
  usePage: () => ({ props: {} }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

beforeEach(() => vi.clearAllMocks());

test.each(['onError', 'onHttpException', 'onNetworkError'])(
  'diagnostic rerun failures show a toast (%s)',
  (callback) => {
    render(
      <Doctor
        checks={[]}
        checks_available={false}
        migrations={[]}
        migration_commands={{ generate: '', apply: '' }}
        dev_server={{ running: false, rows: [] }}
        pages_routed={0}
        stats={{
          checks_passing: 0,
          checks_total: 0,
          modules_loaded: 0,
          pending_migrations: 0,
          python_version: '3.12',
        }}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'dashboard.doctor.rerun' }));
    const [url, , options] = post.mock.calls[0];
    expect(url).toBe('/admin/doctor/rerun');
    options?.[callback]?.({});
    expect(toast.error).toHaveBeenCalledWith('dashboard.doctor.rerun_failed');
  },
);
