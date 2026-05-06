import { usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';

const HEALTH_STATUS_TONE: Record<string, string> = {
  healthy: 'border-emerald-300 bg-emerald-50 text-emerald-700',
  degraded: 'border-amber-300 bg-amber-50 text-amber-700',
  unhealthy: 'border-red-300 bg-red-50 text-red-700',
};

interface SystemModule {
  name: string;
  status: 'loaded';
}

interface HealthCheck {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
}

interface SystemInfo {
  modules: SystemModule[];
  python_version: string;
  health_checks: HealthCheck[];
}

interface Props {
  total_users: number;
  active_users_7d: number;
  module_count: number;
  system_info: SystemInfo;
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function ModuleChip({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border bg-secondary px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
      <span className="h-1.5 w-1.5 rounded-full bg-primary-500" />
      {name}
    </span>
  );
}

function HealthRow({ check }: { check: HealthCheck }) {
  const tone = HEALTH_STATUS_TONE[check.status] ?? HEALTH_STATUS_TONE.unhealthy;
  return (
    <div className="flex items-center gap-3 border-b border-border/60 px-4 py-2.5 text-sm last:border-b-0">
      <span className="flex-1 font-medium">{check.name}</span>
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] ${tone}`}
      >
        {check.status}
      </span>
    </div>
  );
}

function Home() {
  const props = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  return (
    <PageShell
      title={t(keys.dashboard.home.title)}
      description={t(keys.dashboard.home.description)}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard label={t(keys.dashboard.home.stats.total_users)} value={props.total_users} />
        <StatCard label={t(keys.dashboard.home.stats.active_users)} value={props.active_users_7d} />
        <StatCard label={t(keys.dashboard.home.stats.modules)} value={props.module_count} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="rounded-md border bg-card">
          <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
            <span className="text-sm font-semibold">
              {t(keys.dashboard.home.system_info_title)}
            </span>
            <span className="font-mono text-[11px] text-muted-foreground">
              python {props.system_info.python_version}
            </span>
          </div>
          <div>
            {props.system_info.health_checks.map((check) => (
              <HealthRow key={check.name} check={check} />
            ))}
          </div>
        </div>

        <div className="rounded-md border bg-card p-4">
          <div className="text-sm font-semibold">{t(keys.dashboard.home.system_info.modules)}</div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {props.system_info.modules.map((mod) => (
              <ModuleChip key={mod.name} name={mod.name} />
            ))}
          </div>
        </div>
      </div>
    </PageShell>
  );
}

Home.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Home;
