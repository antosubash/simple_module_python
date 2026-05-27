import { router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Empty, EmptyDescription, EmptyMedia, EmptyTitle } from '@simple-module-py/ui/components/ui/empty';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@simple-module-py/ui/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@simple-module-py/ui/components/ui/table';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { ScrollText } from 'lucide-react';
import { useState } from 'react';

interface Change { field: string; old?: unknown; new?: unknown }

interface AuditEntryRead {
  id: string; entity_type: string; entity_id: string;
  action: 'created' | 'updated' | 'deleted' | 'soft_deleted';
  changes: Change[]; user_id: string | null;
  correlation_id: string | null; created_at: string;
}

interface Filters {
  entity_type: string | null; action: string | null; user_id: string | null;
  from_date: string | null; to_date: string | null;
}

interface Props {
  items: AuditEntryRead[]; total: number; page: number; page_size: number;
  entity_types: string[]; filters: Filters;
}

const ALL = '__all__';
const ACTIONS = ['created', 'updated', 'deleted', 'soft_deleted'] as const;
const ACTION_BADGE: Record<string, string> = {
  created: 'border-green-200 bg-green-50 text-green-700',
  updated: 'border-blue-200 bg-blue-50 text-blue-700',
  deleted: 'border-red-200 bg-red-50 text-red-700',
  soft_deleted: 'border-amber-200 bg-amber-50 text-amber-700',
};
const TH = 'text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground';

type TFn = (k: string, p?: Record<string, unknown>) => string;

function ChangesList({ entry, t }: { entry: AuditEntryRead; t: TFn }) {
  const [expanded, setExpanded] = useState(false);
  if (entry.action === 'deleted' || entry.action === 'soft_deleted')
    return <span className="text-muted-foreground">{t(keys.audit_log.changes.no_changes)}</span>;
  if (entry.action === 'created')
    return <span className="text-muted-foreground">{t(keys.audit_log.changes.fields_set, { count: entry.changes.length })}</span>;

  const visible = expanded ? entry.changes : entry.changes.slice(0, 3);
  const remaining = entry.changes.length - 3;
  return (
    <div className="space-y-0.5 text-xs">
      {visible.map((c) => (
        <div key={c.field} className="font-mono">
          <span className="font-semibold">{c.field}</span>{' '}
          <span className="text-muted-foreground">{String(c.old ?? '""')}&rarr;{String(c.new ?? '""')}</span>
        </div>
      ))}
      {remaining > 0 && (
        <button type="button" className="text-primary-700 hover:underline text-xs" onClick={() => setExpanded(!expanded)}>
          {expanded ? t(keys.audit_log.changes.show_less) : t(keys.audit_log.changes.show_more, { count: remaining })}
        </button>
      )}
    </div>
  );
}

function Browse() {
  const { items, total, page, page_size, entity_types, filters } =
    usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  const [entityType, setEntityType] = useState(filters.entity_type ?? ALL);
  const [action, setAction] = useState(filters.action ?? ALL);
  const [userId, setUserId] = useState(filters.user_id ?? '');
  const [fromDate, setFromDate] = useState(filters.from_date ?? '');
  const [toDate, setToDate] = useState(filters.to_date ?? '');

  function navigate(ov: Record<string, string | number | null> = {}) {
    const p: Record<string, string> = {};
    const et = ov.entity_type !== undefined ? ov.entity_type : entityType;
    const act = ov.action !== undefined ? ov.action : action;
    const uid = ov.user_id !== undefined ? ov.user_id : userId;
    const fd = ov.from_date !== undefined ? ov.from_date : fromDate;
    const td = ov.to_date !== undefined ? ov.to_date : toDate;
    const pg = ov.page !== undefined ? ov.page : 1;
    if (et && et !== ALL) p.entity_type = String(et);
    if (act && act !== ALL) p.action = String(act);
    if (uid) p.user_id = String(uid);
    if (fd) p.from_date = String(fd);
    if (td) p.to_date = String(td);
    if (Number(pg) > 1) p.page = String(pg);
    if (page_size !== 50) p.page_size = String(page_size);
    router.visit(`/audit_log?${new URLSearchParams(p).toString()}`);
  }

  function handleClear() {
    setEntityType(ALL); setAction(ALL); setUserId(''); setFromDate(''); setToDate('');
    navigate({ entity_type: ALL, action: ALL, user_id: '', from_date: '', to_date: '' });
  }

  const totalPages = Math.ceil(total / page_size);
  const from = total === 0 ? 0 : (page - 1) * page_size + 1;
  const to = Math.min(page * page_size, total);

  return (
    <PageShell title={t(keys.audit_log.browse.title)} description={t(keys.audit_log.browse.description)}>
      <Card className="mb-4 p-4">
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); navigate(); }}>
          <div className="min-w-[140px]">
            <label className="block text-sm font-medium mb-1">{t(keys.audit_log.filters.entity_type_label)}</label>
            <Select value={entityType} onValueChange={setEntityType}>
              <SelectTrigger size="sm" className="w-full">
                <SelectValue placeholder={t(keys.audit_log.filters.entity_type_all)} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{t(keys.audit_log.filters.entity_type_all)}</SelectItem>
                {entity_types.map((et) => <SelectItem key={et} value={et}>{et}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[130px]">
            <label className="block text-sm font-medium mb-1">{t(keys.audit_log.filters.action_label)}</label>
            <Select value={action} onValueChange={setAction}>
              <SelectTrigger size="sm" className="w-full">
                <SelectValue placeholder={t(keys.audit_log.filters.action_all)} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{t(keys.audit_log.filters.action_all)}</SelectItem>
                {ACTIONS.map((a) => <SelectItem key={a} value={a}>{t(keys.audit_log.actions[a])}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[160px]">
            <label className="block text-sm font-medium mb-1">{t(keys.audit_log.filters.user_label)}</label>
            <Input value={userId} onChange={(e) => setUserId(e.target.value)}
              placeholder={t(keys.audit_log.filters.user_placeholder)} className="h-8 text-sm" />
          </div>
          <div className="min-w-[140px]">
            <label className="block text-sm font-medium mb-1">{t(keys.audit_log.filters.from_date_label)}</label>
            <Input type="datetime-local" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="h-8 text-sm" />
          </div>
          <div className="min-w-[140px]">
            <label className="block text-sm font-medium mb-1">{t(keys.audit_log.filters.to_date_label)}</label>
            <Input type="datetime-local" value={toDate} onChange={(e) => setToDate(e.target.value)} className="h-8 text-sm" />
          </div>
          <Button type="submit" size="sm">{t(keys.audit_log.filters.apply)}</Button>
          <Button type="button" variant="ghost" size="sm" onClick={handleClear}>{t(keys.audit_log.filters.clear)}</Button>
        </form>
      </Card>

      <Card className="border-border overflow-hidden p-0">
        <Table>
          <TableHeader className="bg-secondary/40">
            <TableRow>
              <TableHead className={TH}>{t(keys.audit_log.table.timestamp)}</TableHead>
              <TableHead className={TH}>{t(keys.audit_log.table.action)}</TableHead>
              <TableHead className={TH}>{t(keys.audit_log.table.entity)}</TableHead>
              <TableHead className={`${TH} hidden sm:table-cell`}>{t(keys.audit_log.table.user)}</TableHead>
              <TableHead className={`${TH} hidden md:table-cell`}>{t(keys.audit_log.table.changes)}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((entry) => (
              <TableRow key={entry.id}>
                <TableCell className="whitespace-nowrap text-sm tabular-nums text-muted-foreground">
                  {new Date(entry.created_at).toLocaleString()}
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={ACTION_BADGE[entry.action] ?? ''}>{t(keys.audit_log.actions[entry.action])}</Badge>
                </TableCell>
                <TableCell>
                  <span className="font-medium text-sm">{entry.entity_type}</span>
                  <span className="ml-1 font-mono text-xs text-muted-foreground">{entry.entity_id}</span>
                </TableCell>
                <TableCell className="hidden sm:table-cell text-sm text-muted-foreground">
                  {entry.user_id ?? t(keys.audit_log.changes.system_user)}
                </TableCell>
                <TableCell className="hidden md:table-cell"><ChangesList entry={entry} t={t} /></TableCell>
              </TableRow>
            ))}
            {items.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="h-40">
                  <Empty>
                    <EmptyMedia variant="icon"><ScrollText className="size-5 text-primary-300" /></EmptyMedia>
                    <EmptyTitle>{t(keys.audit_log.browse.empty_title)}</EmptyTitle>
                    <EmptyDescription>{t(keys.audit_log.browse.empty_description)}</EmptyDescription>
                  </Empty>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            {t(keys.audit_log.browse.showing, { from, to, total })}
          </span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => navigate({ page: page - 1 })}>
              {t(keys.audit_log.browse.previous)}
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => navigate({ page: page + 1 })}>
              {t(keys.audit_log.browse.next)}
            </Button>
          </div>
        </div>
      )}
    </PageShell>
  );
}

Browse.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Browse;
