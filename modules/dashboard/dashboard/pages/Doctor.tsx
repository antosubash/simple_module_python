import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { StatCard } from '@simple-module-py/ui/components/StatCard';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { RefreshCw } from 'lucide-react';
import type React from 'react';
import { toast } from 'sonner';
import { ChecksCard } from './components/doctor/ChecksCard';
import { copyToClipboard } from './components/doctor/copy';
import { DevServerCard } from './components/doctor/DevServerCard';
import { MigrationsCard } from './components/doctor/MigrationsCard';
import { buildDoctorReport } from './components/doctor/report';
import { TerminalPanel } from './components/doctor/TerminalPanel';
import type { DoctorProps } from './components/doctor/types';

const RERUN_URL = '/admin/doctor/rerun';

function Doctor() {
  const props = usePage<{ props: DoctorProps }>().props as unknown as DoctorProps;
  const { stats } = props;
  const { t } = useT();

  async function copy(text: string, successMessage: string) {
    if (await copyToClipboard(text)) {
      toast.success(successMessage);
    } else {
      toast.error(t(keys.dashboard.doctor.copy_failed_toast));
    }
  }

  const copyCommand = (command: string) =>
    copy(command, t(keys.dashboard.doctor.copied_command_toast));

  const copyReport = () =>
    copy(
      buildDoctorReport(props, {
        title: t(keys.dashboard.doctor.title),
        checks: t(keys.dashboard.doctor.report_checks),
        migrations: t(keys.dashboard.doctor.report_migrations),
        devServer: t(keys.dashboard.doctor.report_dev_server),
        applied: t(keys.dashboard.doctor.applied),
        pending: t(keys.dashboard.doctor.pending),
        checkLabels: {
          pages: t(keys.dashboard.doctor.checks.pages),
          metadata: t(keys.dashboard.doctor.checks.metadata),
          coupling: t(keys.dashboard.doctor.checks.coupling),
          migrations: t(keys.dashboard.doctor.checks.migrations),
          locales: t(keys.dashboard.doctor.checks.locales),
          inertia: t(keys.dashboard.doctor.checks.inertia),
          auth_provider: t(keys.dashboard.doctor.checks.auth_provider),
          styling: t(keys.dashboard.doctor.checks.styling),
        },
      }),
      t(keys.dashboard.doctor.copied_report_toast),
    );

  return (
    <>
      <Head title={t(keys.dashboard.doctor.title)} />
      <PageShell
        title={t(keys.dashboard.doctor.title)}
        description={
          // Split around the command so it can render in the mono face; the
          // two halves are one sentence and belong together in translation.
          <>
            {t(keys.dashboard.doctor.description_before)}{' '}
            <code className="font-mono text-[13px]">make doctor</code>{' '}
            {t(keys.dashboard.doctor.description_after)}
          </>
        }
        actions={
          <>
            <Button variant="outline" size="sm" onClick={copyReport}>
              {t(keys.dashboard.doctor.copy_report)}
            </Button>
            <Button size="sm" className="gap-1.5" onClick={() => router.post(RERUN_URL)}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              {t(keys.dashboard.doctor.rerun)}
            </Button>
          </>
        }
      >
        <div className="mb-4 grid grid-cols-2 gap-3.5 lg:grid-cols-4">
          <StatCard
            label={t(keys.dashboard.doctor.stat_checks_passing)}
            value={stats.checks_passing}
            suffix={t(keys.dashboard.doctor.stat_checks_total, { count: stats.checks_total })}
          />
          <StatCard
            label={t(keys.dashboard.doctor.stat_modules_loaded)}
            value={stats.modules_loaded}
          />
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

        <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
          <div className="flex flex-col gap-4">
            <ChecksCard
              checks={props.checks}
              available={props.checks_available}
              onCopyCommand={copyCommand}
            />
            <MigrationsCard
              migrations={props.migrations}
              commands={props.migration_commands}
              onCopyCommand={copyCommand}
            />
          </div>
          <div className="flex flex-col gap-4">
            <DevServerCard devServer={props.dev_server} />
            <TerminalPanel props={props} />
          </div>
        </div>
      </PageShell>
    </>
  );
}

Doctor.layout = (page: React.ReactNode) => <AdminLayout>{page}</AdminLayout>;
export default Doctor;
