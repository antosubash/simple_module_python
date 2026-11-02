import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { cn } from '@simple-module-py/ui/lib/utils';

interface PaginationBarProps {
  /** The page being shown (1-based) — echo the server's value, not the URL's. */
  page: number;
  perPage: number;
  total: number;
  onPageChange: (page: number) => void;
  /** Render nothing when everything fits on one page. Off by default: the
   *  "Showing 0–0 of 0" line is how a reader checks a filter matched. */
  hideWhenSinglePage?: boolean;
  className?: string;
}

/**
 * The table footer for any list backed by `simple_module_db.paginate`'s
 * `Page` shape (`page`, `per_page`, `total`): which slice is on screen, plus
 * Previous / Next.
 */
export function PaginationBar({
  page,
  perPage,
  total,
  onPageChange,
  hideWhenSinglePage = false,
  className,
}: PaginationBarProps) {
  const { t } = useT();
  const pages = Math.max(1, Math.ceil(total / Math.max(perPage, 1)));
  if (hideWhenSinglePage && pages <= 1) return null;
  const from = total === 0 ? 0 : (page - 1) * perPage + 1;
  const to = Math.min(page * perPage, total);

  return (
    <div
      className={cn(
        'flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground',
        className,
      )}
    >
      <span>{t(keys.ui.pagination.showing, { from, to, total: total.toLocaleString() })}</span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="max-lg:min-h-11"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          {t(keys.ui.pagination.previous)}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="max-lg:min-h-11"
          disabled={page >= pages}
          onClick={() => onPageChange(page + 1)}
        >
          {t(keys.ui.pagination.next)}
        </Button>
      </div>
    </div>
  );
}
