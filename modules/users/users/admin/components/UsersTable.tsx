import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { ArrowDown, ArrowUp } from 'lucide-react';
import type { Filters } from './IndexFilters';
import { UserCards } from './UserCards';
import { UserRow } from './UserRow';
import { UsersEmptyPanel } from './UsersEmpty';
import type { UserListItem } from './user-list-item';
import { useUserRowActions } from './useUserRowActions';

const HEAD_CLASS =
  'bg-secondary/40 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground';

interface Props {
  users: UserListItem[];
  filters: Filters;
  page: number;
  perPage: number;
  total: number;
  filtered: boolean;
  onSort: (column: Filters['sort']) => void;
  onPage: (page: number) => void;
  onClearFilters: () => void;
}

function SortIcon({ col, filters }: { col: Filters['sort']; filters: Filters }) {
  if (filters.sort !== col) return null;
  return filters.order === 'asc' ? (
    <ArrowUp className="ml-1 inline-block size-3" />
  ) : (
    <ArrowDown className="ml-1 inline-block size-3" />
  );
}

/**
 * The users table, its phone card list, and the footer that pages them.
 *
 * The range and the buttons live inside the card rather than centred beneath
 * it, and stay put on a single page: "Showing 1–7 of 7" is the answer to "is
 * this everyone?", and a control that vanishes when the answer is yes leaves
 * the reader to guess.
 */
export function UsersTable({
  users,
  filters,
  page,
  perPage,
  total,
  filtered,
  onSort,
  onPage,
  onClearFilters,
}: Props) {
  const { t } = useT();
  const actions = useUserRowActions();
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  const from = total === 0 ? 0 : (page - 1) * perPage + 1;
  const to = Math.min(page * perPage, total);

  return (
    <>
      {users.length > 0 && <UserCards users={users} />}
      <Card className="overflow-hidden border-border p-0">
        {users.length === 0 ? (
          <UsersEmptyPanel filtered={filtered} onClear={onClearFilters} />
        ) : (
          // `Table` renders its own scroll container, so hiding the `<table>`
          // alone left that wrapper behind as an empty band above the footer
          // on phones — hide the container instead.
          <div className="hidden sm:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className={HEAD_CLASS}>
                    <button
                      type="button"
                      // The UA stylesheet resets `text-transform` on buttons, so
                      // these two headers alone escaped HEAD_CLASS's `uppercase`.
                      className="flex items-center gap-0.5 uppercase hover:text-foreground"
                      onClick={() => onSort('email')}
                    >
                      {t(keys.users.index.col_member)}
                      <SortIcon col="email" filters={filters} />
                    </button>
                  </TableHead>
                  <TableHead className={HEAD_CLASS}>{t(keys.users.index.col_role)}</TableHead>
                  <TableHead className={HEAD_CLASS}>{t(keys.users.index.col_status)}</TableHead>
                  <TableHead className={`${HEAD_CLASS} hidden lg:table-cell`}>
                    <button
                      type="button"
                      className="flex items-center gap-0.5 uppercase hover:text-foreground"
                      onClick={() => onSort('last_login_at')}
                    >
                      {t(keys.users.index.col_last_seen)}
                      <SortIcon col="last_login_at" filters={filters} />
                    </button>
                  </TableHead>
                  <TableHead className={`${HEAD_CLASS} text-right`} />
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => (
                  <UserRow key={user.id} user={user} actions={actions} />
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        <div className="flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground">
          <span>{t(keys.users.index.showing_range, { from, to, total })}</span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="max-lg:min-h-11"
              disabled={page <= 1}
              onClick={() => onPage(page - 1)}
            >
              {t(keys.users.index.previous)}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="max-lg:min-h-11"
              disabled={page >= totalPages}
              onClick={() => onPage(page + 1)}
            >
              {t(keys.users.index.next)}
            </Button>
          </div>
        </div>
      </Card>
    </>
  );
}
