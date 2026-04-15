import { usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { PageShell } from '@simple-module/ui/components/PageShell';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@simple-module/ui/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from '@simple-module/ui/components/ui/table';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { Activity, Box, Heart, Package, Server, Users } from 'lucide-react';

type Accent = 'primary' | 'emerald' | 'violet' | 'amber';

const HEALTH_STATUS_COLOR: Record<string, string> = {
  healthy: 'bg-emerald-500',
  degraded: 'bg-amber-500',
  unhealthy: 'bg-red-500',
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
  welcome: string;
  total_users: number;
  active_users_7d: number;
  total_products: number;
  module_count: number;
  system_info: SystemInfo;
}

function Home() {
  const props = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  return (
    <PageShell
      title={t(keys.dashboard.home.title)}
      description={t(keys.dashboard.home.description)}
    >
      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-5 mb-8">
        <StatCard
          title={t(keys.dashboard.home.stats.total_users)}
          value={String(props.total_users)}
          icon={<Users className="size-4" />}
          accent="emerald"
        />
        <StatCard
          title={t(keys.dashboard.home.stats.active_users)}
          value={String(props.active_users_7d)}
          icon={<Activity className="size-4" />}
          accent="amber"
        />
        <StatCard
          title={t(keys.dashboard.home.stats.products)}
          value={String(props.total_products)}
          icon={<Package className="size-4" />}
          accent="primary"
        />
        <StatCard
          title={t(keys.dashboard.home.stats.modules)}
          value={String(props.module_count)}
          icon={<Box className="size-4" />}
          accent="violet"
        />
      </div>

      {/* System Info */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-[var(--font-display)]">
            <Server className="size-4" />
            {t(keys.dashboard.home.system_info_title)}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Modules */}
          <div>
            <h4 className="text-sm font-medium text-muted-foreground mb-2">
              {t(keys.dashboard.home.system_info.modules)}
            </h4>
            <div className="flex flex-wrap gap-2">
              {props.system_info.modules.map((mod) => (
                <span
                  key={mod.name}
                  className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium"
                >
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  {mod.name}
                </span>
              ))}
            </div>
          </div>

          {/* Python Version + Health Checks */}
          <Table>
            <TableBody>
              <TableRow>
                <TableCell className="font-medium text-muted-foreground">
                  {t(keys.dashboard.home.system_info.python_version)}
                </TableCell>
                <TableCell>{props.system_info.python_version}</TableCell>
              </TableRow>
              {props.system_info.health_checks.map((check) => (
                <TableRow key={check.name}>
                  <TableCell className="font-medium text-muted-foreground flex items-center gap-2">
                    <Heart className="size-3" />
                    {check.name}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        className={`size-2 rounded-full ${HEALTH_STATUS_COLOR[check.status] ?? 'bg-red-500'}`}
                      />
                      {check.status}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </PageShell>
  );
}

function StatCard({
  title,
  value,
  icon,
  accent,
}: {
  title: string;
  value: string;
  icon: React.ReactNode;
  accent: Accent;
}) {
  const styles: Record<Accent, { card: string; icon: string; value: string }> = {
    primary: {
      card: 'border-primary-200 bg-gradient-to-br from-primary-50 to-card',
      icon: 'text-primary-500 bg-primary-100',
      value: 'text-primary-900',
    },
    emerald: {
      card: 'border-emerald-border bg-gradient-to-br from-emerald-bg to-card',
      icon: 'text-emerald-icon-fg bg-emerald-icon-bg',
      value: 'text-emerald-value',
    },
    violet: {
      card: 'border-violet-border bg-gradient-to-br from-violet-bg to-card',
      icon: 'text-violet-icon-fg bg-violet-icon-bg',
      value: 'text-violet-value',
    },
    amber: {
      card: 'border-amber-200 bg-gradient-to-br from-amber-50 to-card',
      icon: 'text-amber-600 bg-amber-100',
      value: 'text-amber-900',
    },
  };

  const s = styles[accent];

  return (
    <Card className={s.card}>
      <CardContent className="pt-5">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-muted-foreground">{title}</span>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${s.icon}`}>
            {icon}
          </div>
        </div>
        <p className={`text-3xl font-bold font-[var(--font-display)] ${s.value}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

Home.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Home;
