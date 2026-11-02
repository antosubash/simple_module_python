import { Head, router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Trash2 } from 'lucide-react';
import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import { BrowseEmpty } from './components/BrowseEmpty';
import { DropzoneStrip } from './components/DropzoneStrip';
import { FileFilterBar } from './components/FileFilterBar';
import { FileTable } from './components/FileTable';
import { SelectionFooter } from './components/SelectionFooter';
import { UploadDropzone } from './components/UploadDropzone';
import { UploadsCard } from './components/UploadsCard';
import { PERMISSIONS, ROUTES } from './constants';
import { describeTypes, formatBytes } from './format';
import type { BrowseProps, FileFilters } from './types';
import { useUploadQueue } from './upload-queue';
import { useFileActions } from './use-file-actions';

function Browse(props: BrowseProps) {
  const { files, pagination, content_types: contentTypes, uploaders } = props;
  const { t } = useT();
  const { can } = usePermissions();
  const canUpload = can(PERMISSIONS.UPLOAD);
  const canDelete = can(PERMISSIONS.DELETE);
  const { jobs, start, busy, actions } = useUploadQueue({
    directThresholdBytes: props.direct_upload_threshold_bytes,
  });

  const filters: FileFilters = {
    q: props.filters?.q ?? '',
    content_type: props.filters?.content_type ?? '',
    uploaded_by: props.filters?.uploaded_by ?? '',
  };
  const isFiltered = !!(filters.q || filters.content_type || filters.uploaded_by);

  // Selection belongs to the rows on screen: keying it by the page's ids
  // means paging or filtering drops it, so "Delete selected" can never remove
  // something the person can no longer see.
  const pageKey = files.map((f) => f.id).join(',');
  const [selection, setSelection] = useState<{ key: string; ids: string[] }>({
    key: pageKey,
    ids: [],
  });
  const selectedIds = selection.key === pageKey ? selection.ids : [];
  const select = (ids: string[]) => setSelection({ key: pageKey, ids });

  const selectedFiles = files.filter((f) => selectedIds.includes(f.id));
  // One file names its own backend, which is not necessarily the configured
  // one: rows ingested before a backend switch still live where they landed.
  const confirmBackend = selectedFiles.length === 1 ? selectedFiles[0].backend : props.backend;

  const { confirming, setConfirming, deleting, togglePublic, deleteSelected } = useFileActions({
    files,
    selectedIds,
    clearSelection: () => select([]),
  });

  const navigate = useCallback((next: FileFilters, target = 1) => {
    const params: Record<string, string> = {};
    if (next.q) params.q = next.q;
    if (next.content_type) params.content_type = next.content_type;
    if (next.uploaded_by) params.uploaded_by = next.uploaded_by;
    if (target > 1) params.page = String(target);
    router.get(ROUTES.VIEW_BROWSE, params, { preserveState: true, preserveScroll: true });
  }, []);

  // Changing a filter always returns to page 1 — page 4 of the previous
  // filter rarely exists under the new one, and an empty page reads as
  // "no results".
  //
  // Stable identity matters: the filter bar debounces on this callback, so a
  // fresh one each render would clear and restart the timer on every upload
  // progress event and the search would never fire while a file is in flight.
  const applyFilters = useCallback((next: FileFilters) => navigate(next, 1), [navigate]);

  async function handleFiles(picked: File[]) {
    const { uploaded, failed } = await start(picked);
    if (uploaded > 0) {
      toast.success(t(keys.file_storage.toasts.uploaded_count, { count: uploaded }));
    }
    // Failures also leave a row on screen; the toast is for the case where
    // the user has already scrolled away from the card.
    for (const name of failed) {
      toast.error(t(keys.file_storage.toasts.upload_failed_named, { name }));
    }
  }

  const maxSize = formatBytes(props.max_file_size_bytes);
  const subtitle = props.quota_bytes
    ? t(keys.file_storage.browse.subtitle_quota, {
        backend: props.backend,
        used: formatBytes(props.used_bytes),
        quota: formatBytes(props.quota_bytes),
        max: maxSize,
      })
    : t(keys.file_storage.browse.subtitle, {
        backend: props.backend,
        used: formatBytes(props.used_bytes),
        max: maxSize,
      });

  // "Nothing uploaded yet" is wrong — and discouraging — when the bucket is
  // full and the filter is just too narrow. `total` is filter-aware, so this
  // still covers "no matches" without claiming the bucket is empty whenever a
  // page past the last one renders.
  //
  // Upload rows deliberately do *not* suppress it: a failed upload leaves a
  // row in the card above and nothing in the table, and hiding the empty state
  // for it leaves a blank table with no explanation of either fact.
  const showEmpty = files.length === 0 && pagination.total === 0;

  return (
    <>
      <Head title={t(keys.file_storage.browse.head_title)} />
      <PageShell
        title={t(keys.file_storage.browse.title)}
        description={subtitle}
        actions={
          <>
            {canDelete && (
              <Button
                variant="outline"
                className="max-lg:min-h-11"
                disabled={selectedIds.length === 0}
                onClick={() => setConfirming(true)}
              >
                <Trash2 />
                {t(keys.file_storage.browse.delete_selected)}
              </Button>
            )}
            {canUpload && <UploadDropzone onFiles={handleFiles} busy={busy} />}
          </>
        }
      >
        {canUpload && (
          <DropzoneStrip
            onFiles={handleFiles}
            types={
              props.allowed_content_types
                ? describeTypes(props.allowed_content_types)
                : t(keys.file_storage.upload.any_type)
            }
            maxSize={maxSize}
            disabled={busy}
          />
        )}

        <UploadsCard jobs={jobs} actions={actions} />

        <FileFilterBar
          filters={filters}
          facets={contentTypes ?? []}
          uploaders={uploaders ?? []}
          onChange={applyFilters}
        />

        <Card className="gap-0 overflow-hidden p-0">
          <FileTable
            files={files}
            selectedIds={selectedIds}
            canDelete={canDelete}
            canPublish={canUpload}
            onTogglePublic={togglePublic}
            onToggleRow={(id, on) =>
              select(on ? [...selectedIds, id] : selectedIds.filter((x) => x !== id))
            }
            onToggleAll={(on) => select(on ? files.map((f) => f.id) : [])}
            empty={
              showEmpty ? (
                <BrowseEmpty
                  isFiltered={isFiltered}
                  onClear={() => applyFilters({ q: '', content_type: '', uploaded_by: '' })}
                />
              ) : null
            }
          />
          {/* Always visible, one page or forty and empty results included: the
              range is how someone checks their filter matched what they
              expected, and "Showing 0–0 of 0" is the honest answer when it
              matched nothing. */}
          <SelectionFooter
            pagination={pagination}
            selectedCount={selectedIds.length}
            onGo={(target) => navigate(filters, target)}
          />
        </Card>

        {/* `open` stays pinned while the request is in flight: the Radix
            action closes the dialog the moment it is clicked, which would hide
            the busy state it is there to show. */}
        <ConfirmActionDialog
          open={confirming || deleting}
          onOpenChange={(open) => !deleting && setConfirming(open)}
          icon={Trash2}
          title={t(keys.file_storage.delete_dialog.title, {
            count: selectedIds.length,
            name: selectedFiles[0]?.filename ?? '',
          })}
          description={t(keys.file_storage.delete_dialog.description, {
            count: selectedIds.length,
            backend: confirmBackend,
          })}
          confirmLabel={t(keys.file_storage.delete_dialog.confirm, {
            count: selectedIds.length,
          })}
          cancelLabel={t(keys.file_storage.delete_dialog.cancel)}
          busy={deleting}
          onConfirm={deleteSelected}
        />
      </PageShell>
    </>
  );
}

Browse.layout = [AuthenticatedLayout];
export default Browse;
