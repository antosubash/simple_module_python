import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { CopyableId } from '@simple-module-py/ui/components/CopyableId';

export interface EntityRef {
  /** null when no module claims this table — the name renders unlinked. */
  url: string | null;
  /** The kind of row ("User"), for summaries. */
  label: string;
  /** What this particular row is called, or its id when nothing named it. */
  display: string;
  /** `__tablename__`, shown as the muted tag beside the name. */
  table_name: string;
}

export interface AuditEntryRef {
  entity_type: string;
  entity_id: string;
  user_id: string | null;
  /** Display name resolved from user_id, or null for deleted/system actors. */
  actor: string | null;
  /** Where the acting user's record lives, from the audit-link registry. */
  actor_url: string | null;
  entity: EntityRef;
}

const SHORT_ID_LENGTH = 8;
const SHORTEN_ABOVE = 12;

function short(id: string): string {
  return id.length > SHORTEN_ABOVE ? `${id.slice(0, SHORT_ID_LENGTH)}…` : id;
}

/**
 * What changed, by name: "Sam Okafor" with a muted "users_user" beside it.
 *
 * The name comes from the module that owns the row (see the audit-link
 * registry's label resolver) and the tag names the table it lives in, which is
 * the vocabulary the same operator uses in a migration or a psql prompt.
 *
 * Where the row has a link the id rides along as the cell's title — the link
 * itself carries it, so following it is how you get there. Where nothing
 * claims the table there is no link, and the id is the only handle the reader
 * has for querying it elsewhere, so it stays visible and copyable rather than
 * hidden behind a hover.
 */
export function EntityCell({ entry }: { entry: AuditEntryRef }) {
  const display = entry.entity?.display || entry.entity_id;
  const url = entry.entity?.url ?? null;
  const tableName = entry.entity?.table_name || entry.entity_type;
  const named = display !== entry.entity_id;

  return (
    <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
      {url ? (
        <Link
          href={url}
          className="text-sm text-primary-700 hover:underline"
          title={entry.entity_id}
        >
          {display}
        </Link>
      ) : (
        <>
          {named && <span className="text-sm">{display}</span>}
          <CopyableId value={entry.entity_id} label={short(entry.entity_id)} />
        </>
      )}
      <span className="text-xs text-muted-foreground">{tableName}</span>
    </div>
  );
}

/** Who acted: display name where the account still exists, raw id otherwise. */
export function ActorCell({ entry }: { entry: AuditEntryRef }) {
  const { t } = useT();
  if (!entry.user_id) return <>{t(keys.audit_log.changes.system_user)}</>;
  if (entry.actor) {
    // No registered link (users module absent) still shows the name — it is
    // the useful part; the link is a convenience on top.
    if (!entry.actor_url) {
      return <span title={entry.user_id}>{entry.actor}</span>;
    }
    return (
      <Link
        href={entry.actor_url}
        className="text-primary-700 hover:underline"
        title={entry.user_id}
      >
        {entry.actor}
      </Link>
    );
  }
  // The id did not resolve to an account. Show it anyway — it is still the
  // truthful record of who acted — but do not claim to know why. A deleted
  // account and an id from another id space (`celery-worker-1`, which
  // resolve_actors skips by design and which never named an account at all)
  // are indistinguishable from here, so the copy stays neutral.
  return (
    <CopyableId
      value={entry.user_id}
      label={short(entry.user_id)}
      title={t(keys.audit_log.changes.unresolved_user)}
    />
  );
}
