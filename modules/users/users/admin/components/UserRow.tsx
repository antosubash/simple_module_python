import { Link } from '@inertiajs/react';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { TableCell, TableRow } from '@simple-module-py/ui/components/ui/table';
import { Pencil } from 'lucide-react';

export interface UserListItem {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  is_external: boolean;
  last_login_at: string | null;
  created_at: string | null;
  roles: string[];
}

function Avatar({ initial }: { initial: string }) {
  return (
    <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary-600 to-primary-800 text-[13px] font-bold text-white font-[var(--font-display)]">
      {initial}
    </span>
  );
}

function StatusBadge({ user }: { user: UserListItem }) {
  if (!user.is_active) {
    return (
      <Badge variant="outline" className="border-border bg-secondary text-muted-foreground">
        disabled
      </Badge>
    );
  }
  if (!user.is_verified) {
    return (
      <Badge variant="outline" className="border-blue-200 bg-blue-50 text-blue-700">
        invited
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="border-primary-200 bg-primary-50 text-primary-700">
      active
    </Badge>
  );
}

export function UserRow({ user }: { user: UserListItem }) {
  return (
    <TableRow className="hover:bg-secondary/40">
      <TableCell className="py-3">
        <div className="flex items-center gap-3">
          <Avatar initial={(user.full_name || user.email).charAt(0).toUpperCase()} />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-foreground">
              {user.full_name || user.email.split('@')[0]}
            </div>
            <div className="truncate text-[12px] text-muted-foreground">{user.email}</div>
          </div>
        </div>
      </TableCell>
      <TableCell className="hidden sm:table-cell text-sm text-muted-foreground">
        {user.roles.length > 0 ? user.roles.join(', ') : '—'}
      </TableCell>
      <TableCell className="hidden sm:table-cell">
        <div className="flex items-center gap-1.5">
          <StatusBadge user={user} />
          {user.is_external && (
            <Badge variant="outline" className="border-violet-200 bg-violet-50 text-violet-700">
              SSO
            </Badge>
          )}
        </div>
      </TableCell>
      <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
        {user.last_login_at ? new Date(user.last_login_at).toLocaleDateString() : '—'}
      </TableCell>
      <TableCell className="text-right">
        <Button asChild variant="ghost" size="icon-sm">
          <Link href={`/admin/users/${user.id}`}>
            <Pencil />
          </Link>
        </Button>
      </TableCell>
    </TableRow>
  );
}
