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

/** Does `menuUrl` sit at, or below, the route prefix `owner`? */
function isUnder(menuUrl: string, owner: string): boolean {
  const normalized = menuUrl.replace(/\/+$/, '');
  return normalized === owner || normalized.startsWith(`${owner}/`);
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
  // POST entries (Logout) are excluded: the tile renders a GET link, so
  // adopting one as a module's target hands the user a 405.
  const menuUrls = [
    ...(menus?.sidebar ?? []),
    ...(menus?.adminSidebar ?? []),
    ...(menus?.navbar ?? []),
    ...(menus?.userDropdown ?? []),
  ]
    .filter((item) => (item.method ?? 'get') === 'get')
    .map((item) => item.url);

  // Every module's own prefix, so the fallback below can tell "this entry is
  // mine" from "this entry belongs to a module mounted deeper than me".
  const modulePrefixes = props.system_info.modules
    .map((m) => m.url.replace(/\/+$/, ''))
    .filter(Boolean);

  /**
   * The menu entry this module's tile should open, or '' when the user has
   * none.
   *
   * Matching the view prefix exactly is not enough: a module often mounts its
   * landing screen below its own prefix (Users is `/users`, its menu entry is
   * `/users/admin`), and an exact match leaves those tiles permanently inert
   * for admins who can in fact open them. So fall back to the first menu entry
   * that lives under the prefix — but only if no *other* module owns a longer
   * prefix of that entry, or a module mounted at `/admin` would adopt the
   * background-tasks entry at `/admin/background-tasks` and link its tile to
   * somebody else's screen.
   */
  function menuTarget(url: string): string {
    if (!url) return '';
    const prefix = url.replace(/\/+$/, '');
    const exact = menuUrls.find((menuUrl) => menuUrl.replace(/\/+$/, '') === prefix);
    if (exact) return exact;
    return (
      menuUrls.find(
        (menuUrl) =>
          isUnder(menuUrl, prefix) &&
          !modulePrefixes.some((other) => other.length > prefix.length && isUnder(menuUrl, other)),
      ) ?? ''
    );
  }

  const healthLabels: Record<string, string> = {
    healthy: t(keys.dashboard.home.health.healthy),
    degraded: t(keys.dashboard.home.health.degraded),
    unhealthy: t(keys.dashboard.home.health.unhealthy),
  };

  return (
    <>
      <Head title={t(keys.dashboard.home.title)} />
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
            delta={t(keys.dashboard.home.stats.active_users_delta)}
          />
          <StatCard
            label={t(keys.dashboard.home.stats.modules)}
            value={props.module_count}
            icon={Box}
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

        <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
          <Card className="border-border lg:col-span-2">
            <CardContent className="pt-5">
              <SectionTitle
                as="h2"
                right={
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {t(keys.dashboard.home.system_meta, {
                      version: props.system_info.python_version,
                      count: props.module_count,
                    })}
                  </span>
                }
              >
                {t(keys.dashboard.home.system_info_title)}
              </SectionTitle>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                {props.system_info.modules.map((m) => {
                  const target = menuTarget(m.url);
                  return (
                    <ModuleTile
                      key={m.name}
                      name={m.name}
                      url={target}
                      health={m.health}
                      healthLabel={healthLabels[m.health]}
                      reachable={!!target}
                    />
                  );
                })}
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
