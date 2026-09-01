import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { TONE } from '@simple-module-py/ui/lib/tone';
import { Activity, AlertTriangle, Package, RefreshCw, Stethoscope, XCircle } from 'lucide-react';
import type React from 'react';
import { type Diagnostic, DiagnosticsCard } from './components/DiagnosticsCard';
import { type Migration, MigrationsCard } from './components/MigrationsCard';

interface SystemModule {
  name: string;
  status: 'loaded';
}

interface HealthCheck {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
}

interface Environment {
  environment: string;
  database: string;
  locales: string[];
  default_locale: string;
}

interface Props {
  module_count: number;
  system_info: {
    modules: SystemModule[];
    python_version: string;
    health_checks: HealthCheck[];
  };
  diagnostics: Diagnostic[];
  migration: Migration;
  environment: Environment;
}

function Doctor() {
  const props = usePage<{ props: Props }>().props as unknown as Props;
  const { system_info, module_count, diagnostics, migration, environment } = props;
  const { t } = useT();

  const errors = diagnostics.filter((d) => d.level === 'error').length;
  const warnings = diagnostics.filter((d) => d.level === 'warning').length;
  const unhealthy = system_info.health_checks.filter((c) => c.status !== 'healthy').length;

  const envRows: [string, string][] = [
    [t(keys.dashboard.doctor.env_mode), environment.environment],
    [t(keys.dashboard.doctor.env_database), environment.database],
    [t(keys.dashboard.doctor.env_python), system_info.python_version],
    [t(keys.dashboard.doctor.env_locales), environment.locales.join(', ')],
  ];
  if (migration.head_revision) {
    envRows.push([t(keys.dashboard.doctor.env_revision), migration.head_revision.slice(0, 12)]);
  }

  return (
    <>
      <Head title={t(keys.dashboard.doctor.title)} />
      <PageShell
        title={t(keys.dashboard.doctor.title)}
        description={t(keys.dashboard.doctor.description)}
        actions={
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => router.reload()}>
            <RefreshCw className="h-3.5 w-3.5" /> {t(keys.dashboard.doctor.rerun)}
          </Button>
        }
      >
        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard
            label={t(keys.dashboard.doctor.stat_errors)}
            value={errors}
            icon={XCircle}
            delta={errors === 0 ? t(keys.dashboard.doctor.ok) : t(keys.dashboard.doctor.review)}
            deltaTone={errors === 0 ? 'success' : 'destructive'}
          />
          <StatCard
            label={t(keys.dashboard.doctor.stat_warnings)}
            value={warnings}
            icon={AlertTriangle}
            delta={warnings === 0 ? t(keys.dashboard.doctor.ok) : t(keys.dashboard.doctor.review)}
            deltaTone={warnings === 0 ? 'success' : 'warning'}
          />
          <StatCard
            label={t(keys.dashboard.doctor.stat_modules)}
            value={module_count}
            icon={Package}
          />
          <StatCard
            label={t(keys.dashboard.doctor.stat_health)}
            value={
              unhealthy === 0
                ? t(keys.dashboard.doctor.ok)
                : t(keys.dashboard.doctor.alert, { count: unhealthy })
            }
            icon={Activity}
            deltaTone={unhealthy === 0 ? 'success' : 'destructive'}
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
          <div className="flex flex-col gap-4">
            <DiagnosticsCard diagnostics={diagnostics} />
            <MigrationsCard migration={migration} />

            <Card className="border-border">
              <CardContent className="pt-5">
                <SectionTitle>{t(keys.dashboard.doctor.installed_modules)}</SectionTitle>
                <div className="grid gap-2 sm:grid-cols-2">
                  {system_info.modules.map((m) => (
                    <div
                      key={m.name}
                      className="flex items-center gap-2.5 rounded-lg border border-border px-3 py-2.5"
                    >
                      <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-secondary text-muted-foreground">
                        <Package className="h-3.5 w-3.5" aria-hidden="true" />
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="font-mono text-[13px] font-semibold text-foreground truncate">
                          {m.name}
                        </div>
                        <div className="font-mono text-[10px] text-muted-foreground">
                          {t(keys.dashboard.doctor.loaded)}
                        </div>
                      </div>
                      <Badge variant="outline" className={TONE.success}>
                        {t(keys.dashboard.doctor.active)}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="flex flex-col gap-4">
            <Card className="border-border">
              <CardContent className="pt-5">
                <SectionTitle>
                  <Stethoscope className="h-4 w-4" aria-hidden="true" />
                  {t(keys.dashboard.doctor.environment)}
                </SectionTitle>
                <div className="flex flex-col gap-2">
                  {envRows.map(([k, v]) => (
                    <div
                      key={k}
                      className="flex items-center justify-between rounded-lg border border-border px-3 py-2"
                    >
                      <span className="font-mono text-[12px] text-muted-foreground">{k}</span>
                      <Badge variant="outline" className={`${TONE.default} font-mono`}>
                        {v}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card className="border-border">
              <CardContent className="pt-5">
                <SectionTitle>{t(keys.dashboard.doctor.run_command)}</SectionTitle>
                <div className="flex flex-col gap-2 rounded-lg bg-slate-900 p-3 font-mono text-[12px] text-slate-200">
                  {['make new-module name=orders', 'make migrate', 'make doctor', 'make dev'].map(
                    (c) => (
                      <div key={c} className="flex items-center gap-2">
                        <span className="text-primary-300">$</span>
                        <span className="flex-1 truncate">{c}</span>
                      </div>
                    ),
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </PageShell>
    </>
  );
}

Doctor.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Doctor;
