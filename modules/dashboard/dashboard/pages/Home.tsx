import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import type { SharedProps } from '@simple-module-py/ui/types';
import { Activity, Box, Stethoscope, Users } from 'lucide-react';
import { type ModuleHealth, ModuleTile } from './components/ModuleTile';
import { moduleTargetResolver } from './components/module-target';

interface SystemModule {
  name: string;
  status: 'loaded';
  /** The module's own screen, or '' when it ships no views. */
  url: string;
  /** Second mount point for a module that is only partly administrative
   * (`ModuleMeta.admin_view_prefix`), or '' when it declares none. */
  admin_url: string;
  /** Worst health status across the module's checks; '' when it registers none. */
  health: ModuleHealth;
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
  users_created_this_month: number;
  module_count: number;
  system_info: SystemInfo;
}

function Home() {
  const page = usePage();
  const props = page.props as unknown as Props;
  const { menus } = page.props as unknown as SharedProps;
  const { t } = useT();

  const { health_checks: healthChecks } = props.system_info;
  const unhealthy = healthChecks.filter((c) => c.status !== 'healthy').length;
  const moduleTarget = moduleTargetResolver(menus, props.system_info.modules);

  // The third segment of the deck's system meta line. "All checks healthy" is
  // only true when there are checks — a module set that registers none is a
  // different statement, and saying "healthy" there would be a guess.
  const healthSummary =
    healthChecks.length === 0
      ? t(keys.dashboard.home.system_health_none)
      : unhealthy === 0
        ? t(keys.dashboard.home.system_health_ok)
        : t(keys.dashboard.home.system_health_alert, { count: unhealthy });

  const statusLabels: Record<ModuleHealth, string> = {
    '': t(keys.dashboard.home.tile.loaded_no_checks),
    healthy: t(keys.dashboard.home.tile.loaded_healthy),
    degraded: t(keys.dashboard.home.tile.loaded_degraded),
    unhealthy: t(keys.dashboard.home.tile.loaded_unhealthy),
  };

  return (
    <>
      <Head title={t(keys.dashboard.home.title)} />
      <PageShell
        title={t(keys.dashboard.home.title)}
        description={t(keys.dashboard.home.description)}
      >
        <div className="mb-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label={t(keys.dashboard.home.stats.total_users)}
            value={props.total_users}
            icon={Users}
            delta={t(keys.dashboard.home.stats.total_users_delta, {
              count: props.users_created_this_month,
            })}
            deltaTone="secondary"
          />
          <StatCard
            label={t(keys.dashboard.home.stats.active_users)}
            value={props.active_users_7d}
            icon={Activity}
            delta={t(keys.dashboard.home.stats.active_users_delta)}
          />
          <StatCard
            label={t(keys.dashboard.home.stats.modules)}
            value={props.module_count}
            icon={Box}
            delta={t(keys.dashboard.home.stats.modules_delta)}
            deltaTone="secondary"
          />
          <StatCard
            label={t(keys.dashboard.home.stats.health)}
            value={
              unhealthy === 0
                ? t(keys.dashboard.home.health_ok)
                : t(keys.dashboard.home.health_alert, { count: unhealthy })
            }
            icon={Stethoscope}
            delta={
              unhealthy === 0
                ? t(keys.dashboard.home.health_all_good)
                : t(keys.dashboard.home.health_see_doctor)
            }
            deltaTone={unhealthy === 0 ? 'success' : 'warning'}
          />
        </div>

        <Card className="border-border">
          <CardContent className="pt-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-bold font-display">
                {t(keys.dashboard.home.system_info_title)}
              </h2>
              <span className="font-mono text-xs text-muted-foreground">
                {t(keys.dashboard.home.system_meta, {
                  version: props.system_info.python_version,
                  count: props.module_count,
                  health: healthSummary,
                })}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {props.system_info.modules.map((m) => {
                const target = moduleTarget(m.url, m.admin_url);
                return (
                  <ModuleTile
                    key={m.name}
                    name={m.name}
                    url={target}
                    health={m.health}
                    reachable={!!target}
                    statusLabel={statusLabels[m.health]}
                    actionLabel={
                      target
                        ? t(keys.dashboard.home.tile.open)
                        : t(keys.dashboard.home.tile.no_view)
                    }
                  />
                );
              })}
            </div>
          </CardContent>
        </Card>
      </PageShell>
    </>
  );
}

Home.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Home;
