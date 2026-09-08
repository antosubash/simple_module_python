import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@simple-module-py/ui/components/ui/dropdown-menu';
import { MoreHorizontal } from 'lucide-react';
import type { UserListItem } from './user-list-item';
import type { UserRowActions } from './useUserRowActions';

interface Props {
  user: UserListItem;
  actions: UserRowActions;
}

/**
 * The row's "⋯" menu.
 *
 * Everything here is reachable from the edit page too — the menu exists so the
 * common one-click jobs don't cost a page load each. Named per row rather than
 * a bare "Actions", so a screen-reader user tabbing the table hears which
 * account each menu belongs to.
 */
export function UserRowMenu({ user, actions }: Props) {
  const { t } = useT();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={t(keys.users.user_row.actions_aria, { email: user.email })}
          disabled={actions.busy === user.id}
        >
          <MoreHorizontal aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem asChild>
          <Link href={`/admin/users/${user.id}`}>{t(keys.users.user_row.action_edit)}</Link>
        </DropdownMenuItem>
        {/* An SSO account has no local password, so a reset link would point
            at a form that cannot help. */}
        {!user.is_external && (
          <DropdownMenuItem onSelect={() => actions.copyResetLink(user.id)}>
            {t(keys.users.user_row.action_copy_reset)}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem
          variant={user.is_active ? 'destructive' : 'default'}
          onSelect={() => actions.setActive(user.id, !user.is_active)}
        >
          {user.is_active
            ? t(keys.users.user_row.action_disable)
            : t(keys.users.user_row.action_enable)}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
