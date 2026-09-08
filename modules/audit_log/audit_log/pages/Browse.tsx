import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { Download } from 'lucide-react';
import type React from 'react';
import { useState } from 'react';
import { BrowseEmpty } from './components/BrowseEmpty';
import { CorrelationBanner } from './components/Correlation';
import { type AuditEntryRead, EntriesTable } from './components/EntriesTable';
import {
  ALL,
  type AppliedFilters,
  type EntityTypeOption,
  FilterBar,
  type FilterState,
} from './components/FilterBar';
import { Pager } from './components/Pager';

interface Props {
  items: AuditEntryRead[];
  total: number;
  page: number;
  page_size: number;
  entity_types: EntityTypeOption[];
  /** Where the CSV lives; the current filters are appended to it. */
  export_url: string;
  /** `correlation_id` is set only by the per-row "Related" pivot — it has no
   * control in FilterBar. */
  filters: AppliedFilters;
}

const CLEARED: FilterState = {
  entityType: ALL,
  action: ALL,
  userId: '',
  fromDate: '',
  toDate: '',
};

/** The screen's filters as a query string — shared by navigation and the
 * export link, so a CSV can never disagree with the table above it. */
function queryFor(
  next: FilterState,
  correlationId: string | null,
  page: number,
  pageSize: number,
): URLSearchParams {
  const p: Record<string, string> = {};
  if (next.entityType && next.entityType !== ALL) p.entity_type = next.entityType;
  if (next.action && next.action !== ALL) p.action = next.action;
  if (next.userId) p.user_id = next.userId;
  if (correlationId) p.correlation_id = correlationId;
  if (next.fromDate) p.from_date = next.fromDate;
  if (next.toDate) p.to_date = next.toDate;
  if (page > 1) p.page = String(page);
  if (pageSize !== 50) p.page_size = String(pageSize);
  return new URLSearchParams(p);
}

function Browse() {
  const { items, total, page, page_size, entity_types, export_url, filters } = usePage<{
    props: Props;
  }>().props as unknown as Props;
  const { t } = useT();

  const [state, setState] = useState<FilterState>({
    entityType: filters.entity_type ?? ALL,
    action: filters.action ?? ALL,
    userId: filters.user_id ?? '',
    fromDate: filters.from_date ?? '',
    toDate: filters.to_date ?? '',
  });

  // Correlation rides alongside the FilterState rather than inside it: there is
  // no control for it in FilterBar, so it survives an Apply and is dropped only
  // when something asks for it to be.
  function navigate(next: FilterState, nextPage = 1, correlationId = filters.correlation_id) {
    const query = queryFor(next, correlationId, nextPage, page_size);
    // Trailing slash: the browse route is registered at "/" under
    // VIEW_PREFIX and reaches the app via `include_router`, which
    // `_clone_bare_prefix_route` cannot alias — the bare form costs a 307
    // on every filter change. Matches MENU_URL in constants.py.
    router.visit(`/admin/audit-log/?${query.toString()}`);
  }

  function handleClear() {
    setState(CLEARED);
    navigate(CLEARED, 1, null);
  }

  // Pivoting to an action drops the other filters on purpose — the question
  // being asked is "what else did this request touch", and answering it through
  // a filter that already excluded some of those rows would answer it wrongly.
  function handleCorrelationSelect(id: string) {
    setState(CLEARED);
    navigate(CLEARED, 1, id);
  }

  // The applied filters, not the unsubmitted form state: the button must
  // export what the table is showing.
  const exportHref = `${export_url}?${queryFor(
    {
      entityType: filters.entity_type ?? ALL,
      action: filters.action ?? ALL,
      userId: filters.user_id ?? '',
      fromDate: filters.from_date ?? '',
      toDate: filters.to_date ?? '',
    },
    filters.correlation_id,
    1,
    page_size,
  ).toString()}`;

  return (
    <>
      <Head title={t(keys.audit_log.browse.title)} />
      <PageShell
        title={t(keys.audit_log.browse.title)}
        description={t(keys.audit_log.browse.description)}
        actions={
          <Button asChild variant="outline" className="gap-1.5 max-lg:min-h-11">
            <a href={exportHref} download>
              <Download className="size-4" aria-hidden="true" />
              {t(keys.audit_log.browse.export_csv)}
            </a>
          </Button>
        }
      >
        <FilterBar
          state={state}
          entity_types={entity_types}
          onChange={setState}
          onSubmit={() => navigate(state)}
          onClear={handleClear}
        />

        {filters.correlation_id && total > 0 && (
          <CorrelationBanner count={total} onClear={handleClear} />
        )}

        <Card className="border-border overflow-hidden p-0">
          {items.length === 0 ? (
            <BrowseEmpty applied={filters} entityTypes={entity_types} onClear={handleClear} />
          ) : (
            <EntriesTable
              items={items}
              correlationId={filters.correlation_id}
              onCorrelationSelect={handleCorrelationSelect}
            />
          )}

          <Pager
            page={page}
            pageSize={page_size}
            total={total}
            onPage={(next) => navigate(state, next)}
          />
        </Card>
      </PageShell>
    </>
  );
}

Browse.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Browse;
