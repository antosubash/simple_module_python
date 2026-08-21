import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
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
import type React from 'react';
import { useState } from 'react';
import { BrowseEmpty } from './components/BrowseEmpty';
import { CorrelationBanner, CorrelationLink } from './components/Correlation';
import { ActorCell, EntityCell, type EntityRef } from './components/EntryCells';
import { ALL, type AppliedFilters, FilterBar, type FilterState } from './components/FilterBar';

interface Change {
  field: string;
  old?: unknown;
  new?: unknown;
}

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
  entity_types: string[];
  /** `correlation_id` is set only by the per-row "Related" pivot — it has no
   * control in FilterBar. */
  filters: AppliedFilters;
}

const ACTION_BADGE: Record<string, string> = {
  created: 'border-green-200 bg-green-50 text-green-700',
  updated: 'border-blue-200 bg-blue-50 text-blue-700',
  deleted: 'border-red-200 bg-red-50 text-red-700',
  soft_deleted: 'border-amber-200 bg-amber-50 text-amber-700',
};
const TH = 'sm:px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground';

function ChangesList({ entry }: { entry: AuditEntryRead }) {
  const { t } = useT();
  const [expanded, setExpanded] = useState(false);
  if (entry.action === 'deleted' || entry.action === 'soft_deleted')
    return <span className="text-muted-foreground">{t(keys.audit_log.changes.no_changes)}</span>;
  if (entry.action === 'created')
    return (
      <span className="text-muted-foreground">
        {t(keys.audit_log.changes.fields_set, { count: entry.changes.length })}
      </span>
    );

  const visible = expanded ? entry.changes : entry.changes.slice(0, 3);
  const remaining = entry.changes.length - 3;
  return (
    <div className="space-y-0.5 text-xs">
      {visible.map((c) => (
        <div key={c.field} className="font-mono">
          <span className="font-semibold">{c.field}</span>{' '}
          <span className="text-muted-foreground">
            {String(c.old ?? '""')}&rarr;{String(c.new ?? '""')}
          </span>
        </div>
      ))}
      {remaining > 0 && (
        <button
          type="button"
          className="text-primary-700 hover:underline text-xs"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded
            ? t(keys.audit_log.changes.show_less)
            : t(keys.audit_log.changes.show_more, { count: remaining })}
        </button>
      )}
    </div>
  );
}

const CLEARED: FilterState = {
  entityType: ALL,
  action: ALL,
  userId: '',
  fromDate: '',
  toDate: '',
};

function Browse() {
  const { items, total, page, page_size, entity_types, filters } = usePage<{ props: Props }>()
    .props as unknown as Props;
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
    const p: Record<string, string> = {};
    if (next.entityType && next.entityType !== ALL) p.entity_type = next.entityType;
    if (next.action && next.action !== ALL) p.action = next.action;
    if (next.userId) p.user_id = next.userId;
    if (correlationId) p.correlation_id = correlationId;
    if (next.fromDate) p.from_date = next.fromDate;
    if (next.toDate) p.to_date = next.toDate;
    if (nextPage > 1) p.page = String(nextPage);
    if (page_size !== 50) p.page_size = String(page_size);
    // Trailing slash: the browse route is registered at "/" under
    // VIEW_PREFIX and reaches the app via `include_router`, which
    // `_clone_bare_prefix_route` cannot alias — the bare form costs a 307
    // on every filter change. Matches MENU_URL in constants.py.
    router.visit(`/admin/audit-log/?${new URLSearchParams(p).toString()}`);
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

  const totalPages = Math.ceil(total / page_size);
  const from = total === 0 ? 0 : (page - 1) * page_size + 1;
  const to = Math.min(page * page_size, total);

  return (
    <>
      <Head title="Audit Log" />
      <PageShell
        title={t(keys.audit_log.browse.title)}
        description={t(keys.audit_log.browse.description)}
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

        {items.length === 0 ? (
          <BrowseEmpty applied={filters} onClear={handleClear} />
        ) : (
          <Card className="border-border overflow-hidden p-0">
            <Table>
              <TableHeader className="bg-secondary/40">
                <TableRow>
                  <TableHead className={TH}>{t(keys.audit_log.table.timestamp)}</TableHead>
                  <TableHead className={TH}>{t(keys.audit_log.table.action)}</TableHead>
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
                    <TableCell className="sm:px-6 whitespace-nowrap align-top text-sm tabular-nums text-muted-foreground">
                      <div className="flex flex-col">
                        <span>{new Date(entry.created_at).toLocaleString()}</span>
                        {entry.correlation_id && !filters.correlation_id && (
                          <CorrelationLink
                            correlationId={entry.correlation_id}
                            onSelect={handleCorrelationSelect}
                          />
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="sm:px-6">
                      <Badge variant="outline" className={ACTION_BADGE[entry.action] ?? ''}>
                        {t(keys.audit_log.actions[entry.action])}
                      </Badge>
                    </TableCell>
                    <TableCell className="sm:px-6">
                      <EntityCell entry={entry} />
                    </TableCell>
                    <TableCell className="sm:px-6 hidden sm:table-cell text-sm text-muted-foreground">
                      <ActorCell entry={entry} />
                    </TableCell>
                    <TableCell className="sm:px-6 hidden md:table-cell">
                      <ChangesList entry={entry} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}

        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {t(keys.audit_log.browse.showing, { from, to, total })}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => navigate(state, page - 1)}
              >
                {t(keys.audit_log.browse.previous)}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => navigate(state, page + 1)}
              >
                {t(keys.audit_log.browse.next)}
              </Button>
            </div>
          </div>
        )}
      </PageShell>
    </>
  );
}

Browse.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Browse;
