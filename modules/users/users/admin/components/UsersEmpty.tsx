import { Link } from '@inertiajs/react';
import { EmptyState } from '@simple-module-py/ui/components/EmptyState';
import { TableEmptyRow } from '@simple-module-py/ui/components/TableEmptyRow';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Plus, UserPlus, Users } from 'lucide-react';

const ADD_PEOPLE_URL = '/users/admin/add';

// Shared between SoloAccountPrompt and UsersEmptyRow's unfiltered branch —
// both are the same "no other users yet" prompt, just wrapped differently
// (a standalone card above the table vs. the table's own empty row), so the
// copy and call-to-action are declared once here instead of twice.
const INVITE_DESCRIPTION = 'Invite teammates by email, or create accounts with passwords you set.';

function AddPeopleAction() {
  return (
    <Button asChild className="gap-1.5">
      <Link href={ADD_PEOPLE_URL}>
        <Plus className="h-4 w-4" />
        Add people
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
  return (
    <EmptyState
      className="mb-4 rounded-xl border border-dashed border-border bg-card"
      icon={UserPlus}
      title="You're the only account"
      description={INVITE_DESCRIPTION}
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
  return (
    <TableEmptyRow columnCount={columnCount}>
      {filtered ? (
        <EmptyState
          icon={Users}
          title="No users match these filters"
          description="Nobody in this workspace fits the current search and filters."
          action={
            <Button variant="outline" onClick={onClear}>
              Clear filters
            </Button>
          }
        />
      ) : (
        <EmptyState
          icon={UserPlus}
          title="No users yet"
          description={INVITE_DESCRIPTION}
          action={<AddPeopleAction />}
        />
      )}
    </TableEmptyRow>
  );
}
