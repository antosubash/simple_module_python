import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { TableCell, TableRow } from '@simple-module-py/ui/components/ui/table';
import { useRelativeTime } from '@simple-module-py/ui/hooks/use-relative-time';
import { initials } from '@simple-module-py/ui/lib/initials';
import { cn } from '@simple-module-py/ui/lib/utils';
import { StatusPill } from './StatusPill';
import type { UserListItem } from './user-list-item';
import { UserRowMenu } from './UserRowMenu';
import type { UserRowActions } from './useUserRowActions';

/** Two-letter initials on a soft tile — emerald for an account in good standing. */
function Avatar({ user }: { user: UserListItem }) {
  if (user.state === 'invited') {
    // Nobody has accepted yet, so there is no name to abbreviate. A dashed
    // outline says "placeholder" without inventing letters.
    return (
      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-dashed border-border text-xs text-muted-foreground">
        ✉
      </span>
    );
  }
  return (
    <span
      className={cn(
        'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[12px] font-bold',
        user.state === 'active'
          ? 'bg-primary-600/10 text-primary-700'
          : 'bg-secondary text-muted-foreground',
      )}
    >
      {initials(user.full_name, user.email)}
    </span>
  );
}

interface Props {
  user: UserListItem;
  actions: UserRowActions;
}

/**
 * One user, as a table row on `sm` and up.
 *
 * The whole row navigates rather than a pencil in the last cell: the row is
 * already the target the eye is on, and a 16px icon is a poor one. The kebab
 * stops the click from propagating so opening the menu does not also open the
 * page behind it.
 */
export function UserRow({ user, actions }: Props) {
  const { t } = useT();
  const { ago, until } = useRelativeTime();
  const emptyValue = t(keys.users.common.empty_value);
  const invited = user.state === 'invited';

  return (
    <TableRow
      onClick={() => router.visit(`/admin/users/${user.id}`)}
      className={cn(
        'cursor-pointer hover:bg-secondary/40',
        invited && 'bg-amber-500/5',
        // The deck dims the whole disabled row, not just its badge: the
        // account is out of service, and that reads at a glance.
        user.state === 'disabled' && 'opacity-60',
      )}
    >
      <TableCell className="py-3">
        <div className="flex items-center gap-3">
          <Avatar user={user} />
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-foreground">
              {invited ? user.email : user.full_name || user.email.split('@')[0]}
            </div>
            <div className="truncate text-[12.5px] text-muted-foreground">
              {invited
                ? t(keys.users.user_row.invited_meta, {
                    ago: ago(user.invited_at),
                    until: until(user.invite_expires_at),
                  })
                : user.email}
            </div>
          </div>
        </div>
      </TableCell>
      <TableCell className="hidden text-sm text-muted-foreground sm:table-cell">
        {user.roles.length > 0 ? user.roles.join(', ') : emptyValue}
      </TableCell>
      <TableCell className="hidden sm:table-cell">
        <div className="flex items-center gap-1.5">
          <StatusPill state={user.state} />
          {user.is_external && (
            <Badge variant="outline" className="border-violet-200 bg-violet-50 text-violet-700">
              {t(keys.users.user_row.sso_badge)}
            </Badge>
          )}
        </div>
      </TableCell>
      <TableCell className="hidden text-sm text-muted-foreground lg:table-cell">
        {user.last_login_at ? ago(user.last_login_at) : emptyValue}
      </TableCell>
      <TableCell className="text-right whitespace-nowrap">
        {invited && (
          <Button
            variant="ghost"
            size="sm"
            className="text-primary-700 hover:text-primary-800"
            disabled={actions.busy === user.id}
            aria-label={t(keys.users.user_row.resend_aria, { email: user.email })}
            onClick={(event) => {
              event.stopPropagation();
              actions.resendInvite(user.id, user.email);
            }}
          >
            {t(keys.users.user_row.resend)}
          </Button>
        )}
        <UserRowMenu user={user} actions={actions} />
      </TableCell>
    </TableRow>
  );
}
