import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';

import type { Pagination } from '../types';

interface Props {
  pagination: Pagination;
  selectedCount: number;
  onGo: (page: number) => void;
}

/**
 * The table card's foot: what is selected, what is on screen, and the pager.
 *
 * Always rendered, even for a single page — the range is the answer to "did my
 * filter actually match anything?", and a pager that only appears past twenty
 * rows makes people wonder whether it exists at all.
 */
export function SelectionFooter({ pagination, selectedCount, onGo }: Props) {
  const { t } = useT();
  const { page, perPage, total } = pagination;
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  const from = total === 0 ? 0 : (page - 1) * perPage + 1;
  const to = Math.min(page * perPage, total);
  const range = { from, to, total };

  return (
    <div className="flex items-center justify-between gap-3 border-t px-4 py-3 text-sm text-muted-foreground">
      <span>
        {selectedCount > 0
          ? t(keys.file_storage.browse.selected_showing, { count: selectedCount, ...range })
          : t(keys.file_storage.browse.showing, range)}
      </span>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          className="max-lg:min-h-11"
          disabled={page <= 1}
          onClick={() => onGo(page - 1)}
        >
          {t(keys.file_storage.browse.previous)}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="max-lg:min-h-11"
          disabled={page >= totalPages}
          onClick={() => onGo(page + 1)}
        >
          {t(keys.file_storage.browse.next)}
        </Button>
      </div>
    </div>
  );
}
