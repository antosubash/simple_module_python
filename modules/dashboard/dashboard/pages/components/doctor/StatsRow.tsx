import { keys, useT } from '@simple-module-py/i18n';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import type { DoctorStats } from './types';

/** Stands in for a figure that has no value, matching `doctor.py`'s NO_VALUE. */
const NO_VALUE = '—';

interface Props {
  stats: DoctorStats;
  /** False outside development, where the checks never ran. */
  available: boolean;
}

/**
 * The four figures across the top of Doctor.
 *
 * "Checks passing" is the one that cannot simply render its number: on a
 * deployment the checks never ran, and `0 / 8` there reads as every check
 * failing — the precise opposite of the truth. It shows a dash instead, and
 * says why.
 */
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
        value={stats.pending_migrations}
        tone={stats.pending_migrations > 0 ? 'warning' : 'default'}
      />
      <StatCard
        label={t(keys.dashboard.doctor.stat_python)}
        value={stats.python_version}
        valueClassName="text-[22px]"
      />
    </div>
  );
}
