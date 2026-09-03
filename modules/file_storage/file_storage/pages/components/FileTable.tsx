import { keys, useT } from '@simple-module-py/i18n';
import { TableEmptyRow } from '@simple-module-py/ui/components/TableEmptyRow';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Checkbox } from '@simple-module-py/ui/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { useRelativeTime } from '@simple-module-py/ui/hooks/use-relative-time';
import { cn } from '@simple-module-py/ui/lib/utils';

import { ROUTES } from '../constants';
import { formatBytes } from '../format';
import type { StoredFile } from '../types';

interface Props {
  files: StoredFile[];
  selectedIds: string[];
  canDelete: boolean;
  onToggleRow: (id: string, selected: boolean) => void;
  onToggleAll: (selected: boolean) => void;
  /** Rendered in place of the rows when there is nothing to show. */
  empty: React.ReactNode;
}

const HEAD =
  'bg-secondary/40 text-[11px] font-semibold uppercase tracking-[0.08em] ' +
  'text-muted-foreground sm:px-6';

export function FileTable({
  files,
  selectedIds,
  canDelete,
  onToggleRow,
  onToggleAll,
  empty,
}: Props) {
  const { t } = useT();
  const { ago } = useRelativeTime();
  const allSelected = files.length > 0 && selectedIds.length === files.length;
  const columnCount = canDelete ? 7 : 6;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          {canDelete && (
            <TableHead className={cn(HEAD, 'w-10 sm:pr-0')}>
              {/* Indeterminate while only some rows are ticked, so the header
                  box never claims a selection the footer count contradicts. */}
              <Checkbox
                checked={allSelected ? true : selectedIds.length > 0 ? 'indeterminate' : false}
                onCheckedChange={(checked) => onToggleAll(checked === true)}
                aria-label={t(keys.file_storage.table.select_all)}
              />
            </TableHead>
          )}
          <TableHead className={HEAD}>{t(keys.file_storage.table.filename)}</TableHead>
          <TableHead className={cn(HEAD, 'hidden md:table-cell')}>
            {t(keys.file_storage.table.type)}
          </TableHead>
          <TableHead className={HEAD}>{t(keys.file_storage.table.size)}</TableHead>
          <TableHead className={cn(HEAD, 'hidden md:table-cell')}>
            {t(keys.file_storage.table.uploaded_by)}
          </TableHead>
          <TableHead className={cn(HEAD, 'hidden sm:table-cell')}>
            {t(keys.file_storage.table.when)}
          </TableHead>
          <TableHead className={cn(HEAD, 'text-right')}>
            {t(keys.file_storage.table.actions)}
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {files.map((file) => {
          const selected = selectedIds.includes(file.id);
          return (
            <TableRow key={file.id} className={cn(selected && 'bg-primary-600/10')}>
              {canDelete && (
                <TableCell className="sm:pl-6 sm:pr-0">
                  <Checkbox
                    checked={selected}
                    onCheckedChange={(checked) => onToggleRow(file.id, checked === true)}
                    aria-label={t(keys.file_storage.table.select_row, { name: file.filename })}
                  />
                </TableCell>
              )}
              <TableCell className="sm:px-6 font-medium">{file.filename}</TableCell>
              <TableCell className="hidden md:table-cell sm:px-6 text-muted-foreground">
                {file.content_type}
              </TableCell>
              <TableCell className="sm:px-6 tabular-nums text-muted-foreground">
                {formatBytes(file.size_bytes)}
              </TableCell>
              <TableCell className="hidden md:table-cell sm:px-6 text-muted-foreground">
                {file.uploaded_by_label}
              </TableCell>
              <TableCell className="hidden sm:table-cell sm:px-6 text-muted-foreground">
                {ago(file.created_at)}
              </TableCell>
              <TableCell className="text-right sm:px-6">
                <Button
                  asChild
                  variant="link"
                  size="sm"
                  className="h-auto p-0 text-primary-700 max-lg:min-h-11"
                >
                  <a href={ROUTES.apiDownload(file.id)}>{t(keys.file_storage.actions.download)}</a>
                </Button>
              </TableCell>
            </TableRow>
          );
        })}
        {empty && <TableEmptyRow columnCount={columnCount}>{empty}</TableEmptyRow>}
      </TableBody>
    </Table>
  );
}
