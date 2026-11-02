import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { apiResult } from '@simple-module-py/ui/lib/api';
import { useState } from 'react';
import { toast } from 'sonner';
import { api } from './api';
import { RELOAD_PROPS } from './constants';
import type { StoredFile } from './types';

interface Options {
  files: StoredFile[];
  selectedIds: string[];
  /** Called after a bulk delete so the selection does not name removed rows. */
  clearSelection: () => void;
}

/** The mutations Browse can make: flip a file's visibility, delete the selection. */
export function useFileActions({ files, selectedIds, clearSelection }: Options) {
  const { t } = useT();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function togglePublic(file: StoredFile) {
    const result = await apiResult(
      api.PATCH('/api/file-storage/files/{file_id}', {
        params: { path: { file_id: file.id } },
        body: { public: !file.public },
      }),
    );
    if (!result.ok) {
      toast.error(t(keys.file_storage.toasts.visibility_failed));
      return;
    }
    toast.success(
      t(
        file.public ? keys.file_storage.toasts.made_private : keys.file_storage.toasts.made_public,
        {
          name: file.filename,
        },
      ),
    );
    router.reload({ only: RELOAD_PROPS });
  }

  async function deleteSelected() {
    setDeleting(true);
    const result = await apiResult(
      api.POST('/api/file-storage/files/bulk-delete', { body: { ids: selectedIds } }),
    );
    if (!result.ok) {
      toast.error(t(keys.file_storage.toasts.delete_failed));
    } else {
      const { deleted, ids = [] } = result.data;
      // Named from what the server *removed*, not from what was selected: part
      // of a selection can already be gone, and naming the first file the user
      // ticked would credit a deletion that did not happen.
      const removed = ids.length === 1 ? files.find((f) => f.id === ids[0]) : undefined;
      const requested = selectedIds.length;
      if (deleted === 0) {
        // A stale tab: every selected file was removed elsewhere already.
        toast.info(t(keys.file_storage.toasts.already_deleted, { count: requested }));
      } else if (deleted < requested) {
        toast.success(t(keys.file_storage.toasts.deleted_partial, { deleted, total: requested }));
      } else {
        toast.success(
          t(keys.file_storage.toasts.deleted, { count: deleted, name: removed?.filename ?? '' }),
        );
      }
      clearSelection();
      router.reload({ only: RELOAD_PROPS });
    }
    setDeleting(false);
    setConfirming(false);
  }

  return { confirming, setConfirming, deleting, togglePublic, deleteSelected };
}
