import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import type { SharedProps } from '@simple-module-py/ui/types';
import { Activity, Box, Stethoscope, Users } from 'lucide-react';
import { DemoPlaceholders } from './components/DemoPlaceholders';
import { ModuleTile } from './components/ModuleTile';

interface SystemModule {
  name: string;
  status: 'loaded';
  /** The module's own screen, or '' when it ships no views. */
  url: string;
  /** Worst health status across the module's checks; '' when it registers none. */
  health: '' | 'healthy' | 'degraded' | 'unhealthy';
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

function Home() {
  const page = usePage();
  const props = page.props as unknown as Props;
  const { menus } = page.props as unknown as SharedProps;
  const { t } = useT();

  const unhealthy = props.system_info.health_checks.filter((c) => c.status !== 'healthy').length;

  // The server cannot filter these links per user — the stats payload is
  // process-wide cached — so reachability is decided here against the menus
  // the middleware already filtered for this session.
  const reachableUrls = new Set(
    [
      ...(menus?.sidebar ?? []),
      ...(menus?.adminSidebar ?? []),
      ...(menus?.navbar ?? []),
      ...(menus?.userDropdown ?? []),
    ].map((item) => item.url.replace(/\/+$/, '')),
  );

  const healthLabels: Record<string, string> = {
    healthy: t(keys.dashboard.home.health.healthy),
    degraded: t(keys.dashboard.home.health.degraded),
    unhealthy: t(keys.dashboard.home.health.unhealthy),
  };

  return (
    <>
      <Head title="Dashboard" />
      <PageShell
        title={t(keys.dashboard.home.title)}
        description={t(keys.dashboard.home.description)}
      >
        <div className="grid grid-cols-2 gap-3 mb-5 sm:grid-cols-4">
          <StatCard
            label={t(keys.dashboard.home.stats.total_users)}
            value={props.total_users}
            icon={Users}
          />
          <StatCard
            label={t(keys.dashboard.home.stats.active_users)}
            value={props.active_users_7d}
            icon={Activity}
            delta="↑ 7d"
          />
          <StatCard
            label={t(keys.dashboard.home.stats.modules)}
            value={props.module_count}
            icon={Box}
          />
          <StatCard
            label="Health"
            value={unhealthy === 0 ? 'OK' : `${unhealthy} alert`}
            icon={Stethoscope}
            delta={unhealthy === 0 ? 'all good' : 'see Doctor'}
            deltaTone={unhealthy === 0 ? 'success' : 'warning'}
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
          <Card className="border-border lg:col-span-2">
            <CardContent className="pt-5">
              <SectionTitle
                as="h2"
                right={
                  <span className="font-mono text-[11px] text-muted-foreground">
                    Python {props.system_info.python_version} · {props.module_count} modules
                  </span>
                }
              >
                System
              </SectionTitle>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                {props.system_info.modules.map((m) => (
                  <ModuleTile
                    key={m.name}
                    name={m.name}
                    url={m.url}
                    health={m.health}
                    healthLabel={healthLabels[m.health]}
                    reachable={!!m.url && reachableUrls.has(m.url.replace(/\/+$/, ''))}
                  />
                ))}
              </div>
            </CardContent>
          </Card>

          {import.meta.env.DEV && <DemoPlaceholders totalUsers={props.total_users} />}
        </div>
      </PageShell>
    </>
  );
}

Home.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Home;
