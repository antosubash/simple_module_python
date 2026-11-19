import { keys, useT } from '@simple-module-py/i18n';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { NO_VALUE } from './report';
import type { DoctorStats } from './types';

interface Props {
  stats: DoctorStats;
  /** False outside development, where the checks never ran. */
  available: boolean;
}

/** Unavailable checks and unknown migration counts display a dash. */
export function StatsRow({ stats, available }: Props) {
  const { t } = useT();

  return (
    <div className="mb-4 grid grid-cols-2 gap-3.5 lg:grid-cols-4">
      <StatCard
        label={t(keys.dashboard.doctor.stat_checks_passing)}
        value={available ? stats.checks_passing : NO_VALUE}
        suffix={
          available
            ? t(keys.dashboard.doctor.stat_checks_total, { count: stats.checks_total })
            : undefined
        }
        delta={available ? undefined : t(keys.dashboard.doctor.stat_checks_unavailable)}
        deltaTone="secondary"
      />
      <StatCard label={t(keys.dashboard.doctor.stat_modules_loaded)} value={stats.modules_loaded} />
      <StatCard
        label={t(keys.dashboard.doctor.stat_pending_migrations)}
        value={stats.pending_migrations ?? NO_VALUE}
        tone={(stats.pending_migrations ?? 0) > 0 ? 'warning' : 'default'}
      />
      <StatCard
        label={t(keys.dashboard.doctor.stat_python)}
        value={stats.python_version}
        valueClassName="text-[22px]"
      />
    </div>
  );
}
