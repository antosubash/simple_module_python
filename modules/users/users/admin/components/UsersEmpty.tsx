import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { EmptyState } from '@simple-module-py/ui/components/EmptyState';
import { TableEmptyRow } from '@simple-module-py/ui/components/TableEmptyRow';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Plus, UserPlus, Users } from 'lucide-react';

const ADD_PEOPLE_URL = '/users/admin/add';

function AddPeopleAction() {
  const { t } = useT();
  return (
    <Button asChild className="gap-1.5">
      <Link href={ADD_PEOPLE_URL}>
        <Plus className="h-4 w-4" />
        {t(keys.users.empty.add_people)}
      </Link>
    </Button>
  );
}

/**
 * The "you are alone in here" prompt.
 *
 * A workspace with one member renders a perfectly valid table containing the
 * admin's own row, which answers "who has access" without ever suggesting the
 * obvious next step. This sits above that table rather than replacing it: the
 * single row is still the truthful answer to the question the screen asks, and
 * hiding it would cost the admin the only route to their own record.
 */
export function SoloAccountPrompt() {
  const { t } = useT();
  return (
    <EmptyState
      className="mb-4 rounded-xl border border-dashed border-border bg-card"
      icon={UserPlus}
      title={t(keys.users.empty.solo_title)}
      description={t(keys.users.empty.invite_description)}
      action={<AddPeopleAction />}
    />
  );
}

interface UsersEmptyRowProps {
  /** A search term or filter is narrowing the list, so rows may exist outside it. */
  filtered: boolean;
  columnCount: number;
  onClear: () => void;
}

/**
 * The table's own empty row.
 *
 * "No users yet" is both wrong and alarming when the workspace is full and the
 * filter is simply too narrow, so the two cases get opposite copy and opposite
 * actions — clear the filter, or add the first person.
 */
export function UsersEmptyRow({ filtered, columnCount, onClear }: UsersEmptyRowProps) {
  const { t } = useT();
  return (
    <TableEmptyRow columnCount={columnCount}>
      {filtered ? (
        <EmptyState
          icon={Users}
          title={t(keys.users.empty.filtered_title)}
          description={t(keys.users.empty.filtered_description)}
          action={
            <Button variant="outline" onClick={onClear}>
              {t(keys.users.empty.clear_filters)}
            </Button>
          }
        />
      ) : (
        <EmptyState
          icon={UserPlus}
          title={t(keys.users.empty.empty_title)}
          description={t(keys.users.empty.invite_description)}
          action={<AddPeopleAction />}
        />
      )}
    </TableEmptyRow>
  );
}
