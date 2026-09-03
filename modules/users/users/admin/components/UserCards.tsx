import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { useRelativeTime } from '@simple-module-py/ui/hooks/use-relative-time';
import { initials } from '@simple-module-py/ui/lib/initials';
import { cn } from '@simple-module-py/ui/lib/utils';
import { ChevronRight } from 'lucide-react';
import type { UserListItem } from './user-list-item';

/** Amber for the two states that are waiting on something, muted otherwise. */
const META_TONE: Record<UserListItem['state'], string> = {
  active: 'text-muted-foreground',
  unverified: 'text-amber-700 dark:text-amber-400',
  invited: 'text-amber-700 dark:text-amber-400',
  disabled: 'text-muted-foreground',
};

/**
 * The users table folded into cards, for phones.
 *
 * Hiding the Role, Status and Last-seen columns below `sm` left a phone row
 * showing a name, an email and a pencil — the three facts an admin actually
 * scans for were simply gone. A card keeps them on one meta line, and makes
 * the whole card the tap target instead of a 16px icon.
 */
export function UserCards({ users }: { users: UserListItem[] }) {
  const { t } = useT();
  const { ago } = useRelativeTime();

  const metaFor = (user: UserListItem): string => {
    const parts = [
      user.roles[0],
      {
        active: t(keys.users.user_row.status_active),
        unverified: t(keys.users.user_row.status_unverified),
        invited: t(keys.users.user_row.status_invited),
        disabled: t(keys.users.user_row.status_disabled),
      }[user.state],
      user.last_login_at ? ago(user.last_login_at) : null,
    ];
    return parts.filter(Boolean).join(' · ');
  };

  return (
    <div className="space-y-3 sm:hidden">
      {users.map((user) => (
        <Link
          key={user.id}
          href={`/admin/users/${user.id}`}
          aria-label={t(keys.users.user_row.open_aria, { email: user.email })}
          className={cn(
            'flex min-h-11 items-center gap-3 rounded-xl border border-border bg-card p-3.5 shadow-sm',
            user.state === 'disabled' && 'opacity-60',
          )}
        >
          <span
            className={cn(
              'inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[13px] font-bold',
              user.state === 'active'
                ? 'bg-primary-600/10 text-primary-700 dark:text-primary-400'
                : 'bg-secondary text-muted-foreground',
            )}
          >
            {initials(user.full_name, user.email)}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{user.email}</span>
            <span className={cn('mt-0.5 block truncate text-xs', META_TONE[user.state])}>
              {metaFor(user)}
            </span>
          </span>
          <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </Link>
      ))}
    </div>
  );
}
