import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';

interface Props {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}

/** The table footer: which slice is on screen, and the way to the next one.
 *
 * Always rendered, one page or forty: the range is how a reader checks the
 * filter matched what they expected, and "Showing 0–0 of 0" is the honest
 * answer when it matched nothing.
 */
export function Pager({ page, pageSize, total, onPage }: Props) {
  const { t } = useT();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground">
      <span>{t(keys.audit_log.browse.showing, { from, to, total: total.toLocaleString() })}</span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="max-lg:min-h-11"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          {t(keys.audit_log.browse.previous)}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="max-lg:min-h-11"
          disabled={page >= totalPages}
          onClick={() => onPage(page + 1)}
        >
          {t(keys.audit_log.browse.next)}
        </Button>
      </div>
    </div>
  );
}
