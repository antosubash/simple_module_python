import { configureI18n, keys } from '@simple-module-py/i18n';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });
const { post, get } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));
vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  router: { post, get },
  usePage: () => ({ props: {} }),
}));

import Admin from '../sharing/pages/Admin';

const props: ComponentProps<typeof Admin> = {
  shares: [
    {
      id: 'share-1',
      resource_type: 'notes.note',
      resource_id: 'note-1',
      subject_type: 'user',
      subject_id: 'friend',
      subject_label: 'Friend',
      role: 'view',
      granted_by: 'owner',
      granted_by_label: 'Owner',
      expires_at: null,
      expired: false,
      created_at: null,
    },
  ],
  total: 21,
  page: 2,
  per_page: 10,
  can_revoke: true,
  tenant_required: false,
};

afterEach(() => vi.clearAllMocks());

describe('sharing Admin', () => {
  it('shows custom role ids unchanged', () => {
    render(<Admin {...props} shares={[{ ...props.shares[0], role: 'collection_manager' }]} />);
    expect(screen.getByText('collection_manager')).toBeInTheDocument();
  });

  it('renders labels and hides revoke from read-only viewers', () => {
    render(<Admin {...props} can_revoke={false} />);
    expect(screen.getByText('Friend')).toBeInTheDocument();
    expect(screen.getByText('Owner')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: keys.sharing.list.revoke })).toBeNull();
  });

  it('shows the tenant warning instead of shares and pagination when unbound', () => {
    render(<Admin {...props} tenant_required />);
    expect(screen.getByText(keys.sharing.admin.tenant_required)).toBeInTheDocument();
    expect(screen.queryByText('Friend')).toBeNull();
    expect(screen.queryByRole('button', { name: keys.ui.pagination.next })).toBeNull();
  });

  it('shows an empty state without pagination for an empty list', () => {
    render(<Admin {...props} shares={[]} total={0} page={1} />);
    expect(screen.getByText(keys.sharing.list.empty_title)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: keys.ui.pagination.next })).toBeNull();
  });

  it.each([
    [keys.ui.pagination.previous, 1],
    [keys.ui.pagination.next, 3],
  ])('navigates using %s', (name, page) => {
    render(<Admin {...props} />);
    fireEvent.click(screen.getByRole('button', { name }));
    expect(get).toHaveBeenCalledWith('/admin/sharing/', { page }, { preserveScroll: true });
  });

  it.each([1, 3])('disables navigation beyond page %s', (page) => {
    render(<Admin {...props} page={page} />);
    const name = page === 1 ? keys.ui.pagination.previous : keys.ui.pagination.next;
    expect(screen.getByRole('button', { name })).toBeDisabled();
  });

  it('cancels without writing and revokes only after confirmation', async () => {
    render(<Admin {...props} />);
    fireEvent.click(screen.getByRole('button', { name: keys.sharing.list.revoke }));
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole('button', { name: keys.sharing.revoke.cancel }));
    await waitFor(() => expect(screen.queryByText(keys.sharing.revoke.description)).toBeNull());
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: keys.sharing.list.revoke }));
    fireEvent.click(await screen.findByRole('button', { name: keys.sharing.revoke.confirm }));
    expect(post).toHaveBeenCalledWith(
      '/admin/sharing/share-1/revoke',
      {},
      expect.objectContaining({
        preserveScroll: true,
        onFinish: expect.any(Function),
      }),
    );
    expect(screen.getByRole('button', { name: keys.sharing.revoke.confirm })).toBeDisabled();
    act(() => post.mock.calls[0][2].onFinish());
    await waitFor(() => expect(screen.queryByText(keys.sharing.revoke.description)).toBeNull());
  });

  it('clears pending state on visit completion so an unchanged share can be retried', async () => {
    render(<Admin {...props} />);
    fireEvent.click(screen.getByRole('button', { name: keys.sharing.list.revoke }));
    fireEvent.click(await screen.findByRole('button', { name: keys.sharing.revoke.confirm }));
    act(() => post.mock.calls[0][2].onFinish());
    await waitFor(() => expect(screen.queryByText(keys.sharing.revoke.description)).toBeNull());
    expect(screen.getByText('Friend')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: keys.sharing.list.revoke }));
    expect(await screen.findByRole('button', { name: keys.sharing.revoke.confirm })).toBeEnabled();
  });
});
