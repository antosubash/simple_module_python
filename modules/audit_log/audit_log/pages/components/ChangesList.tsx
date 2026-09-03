import { keys, useT } from '@simple-module-py/i18n';
import { useState } from 'react';
import { formatChangePair } from './format';

export interface Change {
  field: string;
  old?: unknown;
  new?: unknown;
}

/**
 * The deck shows two field lines per row and hides the rest behind
 * "+{n} more fields". Two is not a styling detail: the Changes column shares a
 * row with four others, and a settings save that touched nine fields would
 * otherwise make one row as tall as the five around it and push the rest of
 * the page out of view.
 */
const VISIBLE_LIMIT = 2;

interface ChangesListProps {
  action: string;
  changes: Change[];
}

export function ChangesList({ action, changes }: ChangesListProps) {
  const { t } = useT();
  const [expanded, setExpanded] = useState(false);

  // A delete records no diff — every field went away with the row. Saying
  // "no changes recorded" is the honest reading; a dash reads as a bug.
  if (action === 'deleted' || action === 'soft_deleted') {
    return <span className="text-muted-foreground">{t(keys.audit_log.changes.no_changes)}</span>;
  }
  // A create sets every field at once. Listing them all would bury the rows
  // that record an actual change, which is what this column is for.
  if (action === 'created') {
    return (
      <span className="text-muted-foreground">
        {t(keys.audit_log.changes.fields_set, { count: changes.length })}
      </span>
    );
  }

  const visible = expanded ? changes : changes.slice(0, VISIBLE_LIMIT);
  const remaining = changes.length - VISIBLE_LIMIT;

  return (
    <div className="flex flex-col gap-0.5 font-mono text-xs text-muted-foreground">
      {visible.map((change) => (
        <span key={change.field}>
          <span className="text-foreground">{change.field}</span>{' '}
          {formatChangePair(change.old, change.new)}
        </span>
      ))}
      {remaining > 0 && (
        <button
          type="button"
          className="self-start font-sans text-xs font-medium text-primary-700 hover:underline"
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
