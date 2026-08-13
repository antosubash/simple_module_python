import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { CopyableId } from '@simple-module-py/ui/components/CopyableId';

export interface EntityRef {
  /** null when no module claims this table — the id renders unlinked. */
  url: string | null;
  label: string;
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
 * Entity kind and id. The id is a link when the owning module registered one,
 * and always copyable — quoting an id into a ticket is the other thing people
 * do with this column.
 */
export function EntityCell({ entry }: { entry: AuditEntryRef }) {
  const label = entry.entity?.label ?? entry.entity_type;
  const url = entry.entity?.url ?? null;

  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-sm font-medium">{label}</span>
      {url ? (
        <Link href={url} className="font-mono text-xs text-primary-700 hover:underline">
          {short(entry.entity_id)}
        </Link>
      ) : (
        <CopyableId value={entry.entity_id} label={short(entry.entity_id)} />
      )}
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
