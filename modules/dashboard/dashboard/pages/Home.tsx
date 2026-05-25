import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Activity, Box, Stethoscope, Users } from 'lucide-react';
import { DemoPlaceholders } from './components/DemoPlaceholders';

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

function Home() {
  const props = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  const unhealthy = props.system_info.health_checks.filter((c) => c.status !== 'healthy').length;

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
                <div
                  key={m.name}
                  className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2"
                >
                  <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-secondary text-muted-foreground">
                    <Box className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                  <span className="font-mono text-xs text-foreground truncate">{m.name}</span>
                </div>
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
