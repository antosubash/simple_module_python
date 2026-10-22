import { configureI18n, keys } from '@simple-module-py/i18n';
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

const reload = vi.hoisted(() => vi.fn());
vi.mock('@inertiajs/react', () => ({ router: { reload } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { toast } from 'sonner';
import type { StoredFile } from '../file_storage/pages/types';
import { useFileActions } from '../file_storage/pages/use-file-actions';

const files = [
  { id: 'a', filename: 'a.txt', public: false },
  { id: 'b', filename: 'b.txt', public: true },
] as StoredFile[];

function stub(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function setup(selectedIds: string[]) {
  const clearSelection = vi.fn();
  const hook = renderHook(() => useFileActions({ files, selectedIds, clearSelection }));
  return { ...hook, clearSelection };
}

describe('useFileActions', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('PATCHes the flipped visibility and reloads', async () => {
    const fetchMock = stub(200, {});
    const { result } = setup([]);
    await act(() => result.current.togglePublic(files[0]));
    const [req] = fetchMock.mock.calls[0] as unknown as [Request];
    expect(req.method).toBe('PATCH');
    expect(new URL(req.url).pathname).toBe('/api/file-storage/files/a');
    expect(await req.json()).toEqual({ public: true });
    expect(toast.success).toHaveBeenCalledWith(keys.file_storage.toasts.made_public);
    expect(reload).toHaveBeenCalled();
  });

  it('toasts and does not reload when the visibility change fails', async () => {
    stub(403, { detail: 'no' });
    const { result } = setup([]);
    await act(() => result.current.togglePublic(files[0]));
    expect(toast.error).toHaveBeenCalledWith(keys.file_storage.toasts.visibility_failed);
    expect(reload).not.toHaveBeenCalled();
  });

  it('bulk deletes the selection, clears it and closes the dialog', async () => {
    const fetchMock = stub(200, { deleted: 2, ids: ['a', 'b'] });
    const { result, clearSelection } = setup(['a', 'b']);
    act(() => result.current.setConfirming(true));
    await act(() => result.current.deleteSelected());
    const [req] = fetchMock.mock.calls[0] as unknown as [Request];
    expect(new URL(req.url).pathname).toBe('/api/file-storage/files/bulk-delete');
    expect(await req.json()).toEqual({ ids: ['a', 'b'] });
    expect(clearSelection).toHaveBeenCalled();
    expect(result.current.confirming).toBe(false);
    expect(result.current.deleting).toBe(false);
  });

  it('reports a partial delete from what the server removed', async () => {
    stub(200, { deleted: 1, ids: ['a'] });
    const { result } = setup(['a', 'b']);
    await act(() => result.current.deleteSelected());
    expect(toast.success).toHaveBeenCalledWith(keys.file_storage.toasts.deleted_partial);
  });

  it('keeps the selection when the delete fails', async () => {
    stub(500, null);
    const { result, clearSelection } = setup(['a']);
    await act(() => result.current.deleteSelected());
    expect(toast.error).toHaveBeenCalledWith(keys.file_storage.toasts.delete_failed);
    expect(clearSelection).not.toHaveBeenCalled();
    expect(result.current.confirming).toBe(false);
  });
});
