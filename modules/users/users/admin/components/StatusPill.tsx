import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { cn } from '@simple-module-py/ui/lib/utils';
import { STATE_PILL, type UserState } from './user-list-item';

/**
 * One word for where an account stands, in the soft pill the deck uses.
 *
 * Its own module because both the table row and the edit-page header show it,
 * and importing the header's copy out of the row would drag a table cell and
 * an Inertia router into a page that needs neither.
 */
export function StatusPill({ state }: { state: UserState }) {
  const { t } = useT();
  const label = {
    active: t(keys.users.user_row.status_active),
    unverified: t(keys.users.user_row.status_unverified),
    invited: t(keys.users.user_row.status_invited),
    disabled: t(keys.users.user_row.status_disabled),
  }[state];
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium',
        STATE_PILL[state],
      )}
    >
      {label}
    </span>
  );
}

/**
 * Shown beside the status pill while a login lockout holds. Not a state of its
 * own: a locked account is still active, and unlocks itself when the cooldown
 * ends.
 */
export function LockedBadge() {
  const { t } = useT();
  return (
    <Badge
      variant="outline"
      className="border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
    >
      {t(keys.users.user_row.locked_badge)}
    </Badge>
  );
}
