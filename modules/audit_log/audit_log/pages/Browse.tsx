import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { Download } from 'lucide-react';
import type React from 'react';
import { useState } from 'react';
import { BrowseEmpty } from './components/BrowseEmpty';
import { type Change, ChangesList } from './components/ChangesList';
import { CorrelationBanner, CorrelationLink } from './components/Correlation';
import { ActorCell, EntityCell, type EntityRef } from './components/EntryCells';
import {
  ALL,
  type AppliedFilters,
  type EntityTypeOption,
  FilterBar,
  type FilterState,
} from './components/FilterBar';
import { formatEntryTime } from './components/format';

interface AuditEntryRead {
  id: string;
  entity_type: string;
  entity_id: string;
  action: 'created' | 'updated' | 'deleted' | 'soft_deleted';
  changes: Change[];
  user_id: string | null;
  /** Display name resolved from user_id, or null for deleted/system actors. */
  actor: string | null;
  /** Where the acting user's record lives, from the audit-link registry. */
  actor_url: string | null;
  entity: EntityRef;
  correlation_id: string | null;
  created_at: string;
}

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

// Borderless tints, lowercase values: the pill is a value in a dense table,
// not a badge competing with the row's links for attention.
const ACTION_PILL: Record<string, string> = {
  created: 'bg-primary-600/10 text-primary-700',
  updated: 'bg-blue-50 text-blue-700',
  deleted: 'bg-red-50 text-red-700',
  soft_deleted: 'bg-amber-50 text-amber-700',
};
const PILL = 'inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-medium';
const TH = 'sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground';
const TD = 'sm:px-6 align-top';

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

  const totalPages = Math.max(1, Math.ceil(total / page_size));
  const from = total === 0 ? 0 : (page - 1) * page_size + 1;
  const to = Math.min(page * page_size, total);
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
            <Table>
              <TableHeader className="bg-secondary/40">
                <TableRow>
                  <TableHead className={`${TH} w-[150px]`}>
                    {t(keys.audit_log.table.timestamp)}
                  </TableHead>
                  <TableHead className={`${TH} w-[110px]`}>
                    {t(keys.audit_log.table.action)}
                  </TableHead>
                  <TableHead className={TH}>{t(keys.audit_log.table.entity)}</TableHead>
                  <TableHead className={`${TH} hidden sm:table-cell`}>
                    {t(keys.audit_log.table.user)}
                  </TableHead>
                  <TableHead className={`${TH} hidden md:table-cell`}>
                    {t(keys.audit_log.table.changes)}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((entry) => (
                  <TableRow key={entry.id} className="hover:bg-secondary/40">
                    <TableCell
                      className={`${TD} whitespace-nowrap font-mono text-xs text-muted-foreground`}
                    >
                      <div className="flex flex-col">
                        <span>{formatEntryTime(entry.created_at)}</span>
                        {/* The deck has no correlation control. It stays here
                            because it is the only way back from one row to the
                            request that wrote it, and under the timestamp is
                            where "this same moment" belongs. */}
                        {entry.correlation_id && !filters.correlation_id && (
                          <CorrelationLink
                            correlationId={entry.correlation_id}
                            onSelect={handleCorrelationSelect}
                          />
                        )}
                      </div>
                    </TableCell>
                    <TableCell className={TD}>
                      <span className={`${PILL} ${ACTION_PILL[entry.action] ?? ''}`}>
                        {t(keys.audit_log.actions[entry.action])}
                      </span>
                    </TableCell>
                    <TableCell className={`${TD} whitespace-normal`}>
                      <EntityCell entry={entry} />
                    </TableCell>
                    <TableCell
                      className={`${TD} hidden sm:table-cell text-sm text-muted-foreground`}
                    >
                      <ActorCell entry={entry} />
                    </TableCell>
                    {/* `TableCell` is `whitespace-nowrap` by default, which
                        made one long value push the table wider than the card
                        and cut every updated row mid-value. */}
                    <TableCell className={`${TD} hidden whitespace-normal md:table-cell`}>
                      <ChangesList action={entry.action} changes={entry.changes} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Always visible, one page or forty: the range is how a reader
              checks the filter matched what they expected, and "Showing 0–0
              of 0" is the honest answer when it matched nothing. */}
          <div className="flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground">
            <span>
              {t(keys.audit_log.browse.showing, { from, to, total: total.toLocaleString() })}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="max-lg:min-h-11"
                disabled={page <= 1}
                onClick={() => navigate(state, page - 1)}
              >
                {t(keys.audit_log.browse.previous)}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="max-lg:min-h-11"
                disabled={page >= totalPages}
                onClick={() => navigate(state, page + 1)}
              >
                {t(keys.audit_log.browse.next)}
              </Button>
            </div>
          </div>
        </Card>
      </PageShell>
    </>
  );
}

Browse.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Browse;
