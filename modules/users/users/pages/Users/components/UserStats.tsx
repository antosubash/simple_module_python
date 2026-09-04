import { keys, useT } from '@simple-module-py/i18n';
import { StatCard } from '@simple-module-py/ui/components/StatCard';

interface Props {
  total: number;
  active: number;
  invited: number;
  roleCount: number;
}

/**
 * The four headline counts above the users table.
 *
 * Plain label-over-number cards: an icon tile and a "review"/"all set" badge
 * on every card turned a row meant to be read in one sweep into four small
 * compositions. Only "Pending invites" is coloured, and only because it is the
 * one figure here that asks for an action.
 */
export function UserStats({ total, active, invited, roleCount }: Props) {
  const { t } = useT();
  return (
    <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard label={t(keys.users.index.stat_members)} value={total} />
      <StatCard label={t(keys.users.index.stat_active)} value={active} />
      <StatCard
        label={t(keys.users.index.stat_pending)}
        value={invited}
        valueClassName={invited > 0 ? 'text-amber-700 dark:text-amber-400' : undefined}
      />
      <StatCard label={t(keys.users.index.stat_roles)} value={roleCount} />
    </div>
  );
}
