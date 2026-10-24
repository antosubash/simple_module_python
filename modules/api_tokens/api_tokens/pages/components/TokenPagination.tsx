import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import type { TokenFormProps } from '../types';

export function TokenPagination({ limit, offset, has_more }: TokenFormProps['pagination']) {
  const { t } = useT();
  function visit(nextOffset: number) {
    router.get(window.location.pathname, { limit, offset: nextOffset }, { preserveState: true });
  }
  return (
    <div className="flex justify-end gap-2">
      <Button
        variant="outline"
        disabled={offset === 0}
        onClick={() => visit(Math.max(0, offset - limit))}
      >
        {t(keys.ui.pagination.previous)}
      </Button>
      <Button variant="outline" disabled={!has_more} onClick={() => visit(offset + limit)}>
        {t(keys.ui.pagination.next)}
      </Button>
    </div>
  );
}
