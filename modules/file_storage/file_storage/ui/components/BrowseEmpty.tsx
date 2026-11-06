import { keys, useT } from '@simple-module-py/i18n';
import { EmptyState } from '@simple-module-py/ui/components/EmptyState';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { FileBox } from 'lucide-react';

interface Props {
  isFiltered: boolean;
  onClear: () => void;
}

/** The table's empty state: an empty bucket, or a filter that matched nothing. */
export function BrowseEmpty({ isFiltered, onClear }: Props) {
  const { t } = useT();
  return (
    <EmptyState
      icon={FileBox}
      title={
        isFiltered
          ? t(keys.file_storage.browse.no_match_title)
          : t(keys.file_storage.browse.empty_title)
      }
      description={
        isFiltered
          ? t(keys.file_storage.browse.no_match_description)
          : t(keys.file_storage.browse.empty_description)
      }
      action={
        isFiltered ? (
          <Button variant="outline" onClick={onClear}>
            {t(keys.file_storage.browse.clear_filters)}
          </Button>
        ) : undefined
      }
    />
  );
}
