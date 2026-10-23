import { configureI18n } from '@simple-module-py/i18n';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, expect, test, vi } from 'vitest';
import Admin from '../sharing/pages/Admin';

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
  'revoke failures show a toast and release the busy dialog (%s)',
  (callback) => {
    render(
      <Admin
        shares={[
          {
            id: 's1',
            resource_type: 'order',
            resource_id: 'o1',
            subject_type: 'user',
            subject_id: 'u1',
            subject_label: null,
            role: 'viewer',
            granted_by: 'u2',
            granted_by_label: null,
            expires_at: null,
            expired: false,
            created_at: null,
          },
        ]}
        total={1}
        page={1}
        per_page={20}
        can_revoke
        tenant_required={false}
      />,
    );
    fireEvent.click(screen.getAllByRole('button', { name: 'sharing.list.revoke' })[0]);
    fireEvent.click(
      within(screen.getByRole('alertdialog')).getByRole('button', {
        name: 'sharing.revoke.confirm',
      }),
    );
    const [url, , options] = post.mock.calls[0];
    expect(url).toBe('/admin/sharing/s1/revoke');
    act(() => {
      options[callback]({});
      options.onFinish();
    });
    expect(toast.error).toHaveBeenCalledWith('sharing.revoke.failed');
    expect(screen.queryByRole('alertdialog')).toBeNull();
  },
);
