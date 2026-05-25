import { Head, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  GitBranch,
  Package,
  Play,
  RefreshCw,
  Stethoscope,
  Terminal,
  XCircle,
} from 'lucide-react';
import { DEV_SERVER, ENV_VARS, MIGRATIONS, STATIC_CHECKS, TONE } from './components/doctor-data';

interface SystemModule {
  name: string;
  status: 'loaded';
}

interface HealthCheck {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
}

interface Props {
  total_users: number;
  active_users_7d: number;
  module_count: number;
  system_info: {
    modules: SystemModule[];
    python_version: string;
    health_checks: HealthCheck[];
  };
}

const STATUS_VISUALS = {
  pass: { Icon: CheckCircle2, color: 'text-primary-600', tone: TONE.success },
  warn: { Icon: AlertTriangle, color: 'text-amber-600', tone: TONE.warning },
  fail: { Icon: XCircle, color: 'text-red-600', tone: TONE.destructive },
} as const;

function CheckRow({ check }: { check: (typeof STATIC_CHECKS)[number] }) {
  const { Icon, color, tone } = STATUS_VISUALS[check.status];
  return (
    <div className="flex items-start gap-3 border-t border-border px-1 py-3 first:border-t-0">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color}`} aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-foreground">{check.name}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">{check.hint}</div>
        {'file' in check && check.file && (
          <code className="mt-1 inline-block font-mono text-[11px] text-muted-foreground">
            {check.file}
          </code>
        )}
      </div>
      <Badge variant="outline" className={tone}>
        {check.status}
      </Badge>
    </div>
  );
}

function Doctor() {
  const { system_info, module_count } = usePage<{ props: Props }>().props as unknown as Props;

  const passed = STATIC_CHECKS.filter((c) => c.status === 'pass').length;
  const pending = MIGRATIONS.filter((m) => !m.applied).length;
  const unhealthy = system_info.health_checks.filter((c) => c.status !== 'healthy').length;

  return (
    <>
    <Head title="Doctor" />
    <PageShell
      title="Doctor"
      description="Static checks, migrations, dev server, and module health. Mirrors `make doctor` output."
      actions={
        <>
          <Button variant="outline" size="sm" className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" /> Re-run
          </Button>
          <Button size="sm" className="gap-1.5">
            <Terminal className="h-3.5 w-3.5" /> make doctor
          </Button>
        </>
      }
    >
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Checks passed"
          value={`${passed}/${STATIC_CHECKS.length}`}
          icon={CheckCircle2}
          delta={passed === STATIC_CHECKS.length ? 'OK' : 'review'}
          deltaTone={passed === STATIC_CHECKS.length ? 'success' : 'warning'}
        />
        <StatCard label="Modules" value={module_count} icon={Package} />
        <StatCard
          label="Pending mig."
          value={pending}
          icon={Database}
          delta={pending === 0 ? 'clean' : 'review'}
          deltaTone={pending === 0 ? 'success' : 'warning'}
        />
        <StatCard
          label="Health"
          value={unhealthy === 0 ? 'OK' : `${unhealthy} alert`}
          icon={Activity}
          deltaTone={unhealthy === 0 ? 'success' : 'destructive'}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-4">
          <Card className="border-border">
            <CardContent className="pt-5">
              <SectionTitle
                right={
                  <span className="font-mono text-[11px] text-muted-foreground">just now</span>
                }
              >
                Static checks
              </SectionTitle>
              <div className="-mx-1">
                {STATIC_CHECKS.map((c) => (
                  <CheckRow key={c.name} check={c} />
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-border">
            <CardContent className="pt-5">
              <SectionTitle
                right={
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" className="gap-1.5">
                      <GitBranch className="h-3.5 w-3.5" /> Generate
                    </Button>
                    <Button variant="ghost" size="sm" className="gap-1.5">
                      <Play className="h-3.5 w-3.5" /> Apply
                    </Button>
                  </div>
                }
              >
                Recent migrations
              </SectionTitle>
              <div className="-mx-1">
                {MIGRATIONS.map((m) => (
                  <div
                    key={m.id}
                    className="flex items-center gap-3 border-t border-border px-1 py-3 first:border-t-0"
                  >
                    <code className="w-14 shrink-0 font-mono text-[11px] text-muted-foreground">
                      {m.id}
                    </code>
                    <Badge variant="outline" className={TONE.default}>
                      {m.module}
                    </Badge>
                    <div className="flex-1 truncate text-sm text-foreground">{m.msg}</div>
                    <span className="font-mono text-[11px] text-muted-foreground">{m.when}</span>
                    <Badge variant="outline" className={m.applied ? TONE.success : TONE.warning}>
                      {m.applied ? 'applied' : 'pending'}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-border">
            <CardContent className="pt-5">
              <SectionTitle>Installed modules</SectionTitle>
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
                      <div className="font-mono text-[10px] text-muted-foreground">loaded</div>
                    </div>
                    <Badge variant="outline" className={TONE.success}>
                      active
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
              <SectionTitle
                right={
                  <span className="flex items-center gap-1.5 font-mono text-[11px] text-primary-700">
                    <span className="h-2 w-2 rounded-full bg-primary-600 ring-4 ring-primary-200" />
                    running
                  </span>
                }
              >
                Dev server
              </SectionTitle>
              <div className="flex flex-col gap-2">
                {DEV_SERVER.map(([k, v, tone]) => (
                  <div
                    key={k}
                    className="flex items-center justify-between rounded-lg border border-border px-3 py-2"
                  >
                    <span className="font-mono text-[12px] text-muted-foreground">{k}</span>
                    <Badge variant="outline" className={TONE[tone]}>
                      {v}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-border">
            <CardContent className="pt-5">
              <SectionTitle>Run a command</SectionTitle>
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

          <Card className="border-border">
            <CardContent className="pt-5">
              <SectionTitle>
                <Stethoscope className="h-4 w-4" aria-hidden="true" />
                Environment
              </SectionTitle>
              <div className="flex flex-col gap-2 text-[13px]">
                {ENV_VARS.map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between">
                    <code className="font-mono text-[11px] text-muted-foreground">{k}</code>
                    <Badge variant="outline" className={TONE.default}>
                      {v}
                    </Badge>
                  </div>
                ))}
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
