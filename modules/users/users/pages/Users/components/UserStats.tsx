import { keys, useT } from '@simple-module-py/i18n';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { Mail, ShieldCheck, UserCheck, Users } from 'lucide-react';

interface Props {
  total: number;
  active: number;
  unverified: number;
  roleCount: number;
}

/** The four headline counts above the users table. */
export function UserStats({ total, active, unverified, roleCount }: Props) {
  const { t } = useT();
  const pending = unverified > 0;
  return (
    <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard label={t(keys.users.index.stat_members)} value={total} icon={Users} />
      <StatCard label={t(keys.users.index.stat_active)} value={active} icon={UserCheck} />
      <StatCard
        label={t(keys.users.index.stat_pending)}
        value={unverified}
        icon={Mail}
        delta={pending ? t(keys.users.index.pending_review) : t(keys.users.index.pending_all_set)}
        deltaTone={pending ? 'warning' : 'success'}
      />
      <StatCard label={t(keys.users.index.stat_roles)} value={roleCount} icon={ShieldCheck} />
    </div>
  );
}
