import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@simple-module-py/ui/components/ui/alert-dialog';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from '@simple-module-py/ui/components/ui/empty';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { usePermissions } from '@simple-module-py/ui/hooks/use-permissions';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Download, FileBox, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { UploadDropzone } from './components/UploadDropzone';
import { PERMISSIONS, ROUTES, UNKNOWN_UPLOADER } from './constants';

interface StoredFile {
  id: string;
  filename: string;
  size_bytes: number;
  content_type: string;
  uploaded_by: string | null;
  created_at: string | null;
}

interface Pagination {
  page: number;
  perPage: number;
  total: number;
}

interface Props {
  files: StoredFile[];
  pagination: Pagination;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function Browse() {
  const page = usePage<{ props: Props }>();
  const { files, pagination } = page.props as unknown as Props;
  const { t } = useT();
  const { can } = usePermissions();
  const canUpload = can(PERMISSIONS.UPLOAD);
  const canDelete = can(PERMISSIONS.DELETE);

  function handleDelete(file: StoredFile) {
    fetch(ROUTES.apiFile(file.id), { method: 'DELETE' })
      .then((resp) => {
        if (!resp.ok) throw new Error('delete failed');
        toast.success(t(keys.file_storage.toasts.deleted, { name: file.filename }));
        router.reload({ only: ['files', 'pagination'] });
      })
      .catch(() => toast.error(t(keys.file_storage.toasts.delete_failed)));
  }

  return (
    <>
      <Head title="File Storage" />
      <PageShell
        title={t(keys.file_storage.browse.title)}
        description={t(keys.file_storage.browse.description)}
        actions={canUpload ? <UploadDropzone /> : undefined}
      >
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="sm:px-6">{t(keys.file_storage.table.filename)}</TableHead>
                <TableHead className="hidden md:table-cell sm:px-6">
                  {t(keys.file_storage.table.type)}
                </TableHead>
                <TableHead className="sm:px-6">{t(keys.file_storage.table.size)}</TableHead>
                <TableHead className="hidden md:table-cell sm:px-6">
                  {t(keys.file_storage.table.uploaded_by)}
                </TableHead>
                <TableHead className="text-right sm:px-6">
                  {t(keys.file_storage.table.actions)}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {files.map((file) => (
                <TableRow key={file.id}>
                  <TableCell className="sm:px-6 font-medium">{file.filename}</TableCell>
                  <TableCell className="hidden md:table-cell sm:px-6 text-muted-foreground">
                    {file.content_type}
                  </TableCell>
                  <TableCell className="sm:px-6 tabular-nums text-muted-foreground">
                    {formatBytes(file.size_bytes)}
                  </TableCell>
                  <TableCell className="hidden md:table-cell sm:px-6 text-muted-foreground">
                    {file.uploaded_by ?? UNKNOWN_UPLOADER}
                  </TableCell>
                  <TableCell className="text-right sm:px-6">
                    <div className="flex items-center justify-end gap-1">
                      <Button asChild variant="ghost" size="icon-sm">
                        <a
                          href={ROUTES.apiDownload(file.id)}
                          aria-label={t(keys.file_storage.actions.download)}
                        >
                          <Download />
                        </a>
                      </Button>
                      {canDelete && (
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              className="text-destructive hover:text-destructive"
                            >
                              <Trash2 />
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>
                                {t(keys.file_storage.delete_dialog.title, { name: file.filename })}
                              </AlertDialogTitle>
                              <AlertDialogDescription>
                                {t(keys.file_storage.delete_dialog.description)}
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>
                                {t(keys.file_storage.delete_dialog.cancel)}
                              </AlertDialogCancel>
                              <AlertDialogAction
                                onClick={() => handleDelete(file)}
                                className="bg-destructive text-white hover:bg-destructive/90"
                              >
                                {t(keys.file_storage.delete_dialog.confirm)}
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {files.length === 0 && pagination.total === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="h-40">
                    <Empty>
                      <EmptyMedia variant="icon">
                        <FileBox className="size-5 text-primary-300" />
                      </EmptyMedia>
                      <EmptyTitle>{t(keys.file_storage.browse.empty_title)}</EmptyTitle>
                      <EmptyDescription>
                        {t(keys.file_storage.browse.empty_description)}
                      </EmptyDescription>
                    </Empty>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Card>
      </PageShell>
    </>
  );
}

Browse.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Browse;
