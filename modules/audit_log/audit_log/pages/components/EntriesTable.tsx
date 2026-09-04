import { keys, useT } from '@simple-module-py/i18n';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { type Change, ChangesList } from './ChangesList';
import { CorrelationLink } from './Correlation';
import { ActorCell, EntityCell, type EntityRef } from './EntryCells';
import { formatEntryTime } from './format';

export interface AuditEntryRead {
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
  /** The subject row. `display` falls back to the stored id when the owning
   * module named no resolver — or gated it behind a permission this reader
   * does not hold, which is why a name can be absent for an admin and present
   * for another (see `AuditLink.label_permission`). */
  entity: EntityRef;
  correlation_id: string | null;
  created_at: string;
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

interface Props {
  items: AuditEntryRead[];
  /** The correlation currently being filtered on, if any — a row already
   * inside that pivot has nowhere further to pivot to, so its link is hidden. */
  correlationId: string | null;
  onCorrelationSelect: (id: string) => void;
}

/** The audit table itself: five columns, one row per entry.
 *
 * Split out of `Browse` so the page keeps its filter/pagination/navigation
 * logic in one screenful and the row rendering in another — the two change for
 * unrelated reasons, and together they sat against the 300-line cap.
 */
export function EntriesTable({ items, correlationId, onCorrelationSelect }: Props) {
  const { t } = useT();

  return (
    <Table>
      <TableHeader className="bg-secondary/40">
        <TableRow>
          <TableHead className={`${TH} w-[150px]`}>{t(keys.audit_log.table.timestamp)}</TableHead>
          <TableHead className={`${TH} w-[110px]`}>{t(keys.audit_log.table.action)}</TableHead>
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
                {/* The deck has no correlation control. It stays here because
                    it is the only way back from one row to the request that
                    wrote it, and under the timestamp is where "this same
                    moment" belongs. */}
                {entry.correlation_id && !correlationId && (
                  <CorrelationLink
                    correlationId={entry.correlation_id}
                    onSelect={onCorrelationSelect}
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
            <TableCell className={`${TD} hidden sm:table-cell text-sm text-muted-foreground`}>
              <ActorCell entry={entry} />
            </TableCell>
            {/* `TableCell` is `whitespace-nowrap` by default, which made one
                long value push the table wider than the card and cut every
                updated row mid-value. */}
            <TableCell className={`${TD} hidden whitespace-normal md:table-cell`}>
              <ChangesList action={entry.action} changes={entry.changes} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
