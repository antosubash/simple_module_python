import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AdminLayout } from '@simple-module-py/ui/layouts/AdminLayout';
import { RefreshCw } from 'lucide-react';
import type React from 'react';
import { toast } from 'sonner';
import { ChecksCard } from './components/doctor/ChecksCard';
import { useCheckLabels } from './components/doctor/check-copy';
import { copyToClipboard } from './components/doctor/copy';
import { DevServerCard } from './components/doctor/DevServerCard';
import { MigrationsCard } from './components/doctor/MigrationsCard';
import { buildDoctorReport } from './components/doctor/report';
import { StatsRow } from './components/doctor/StatsRow';
import { TerminalPanel } from './components/doctor/TerminalPanel';
import type { DoctorProps } from './components/doctor/types';

const RERUN_URL = '/admin/doctor/rerun';

function Doctor() {
  const props = usePage<{ props: DoctorProps }>().props as unknown as DoctorProps;
  const { t } = useT();
  const checkLabels = useCheckLabels();

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
        checksUnavailable: t(keys.dashboard.doctor.report_checks_unavailable),
        migrations: t(keys.dashboard.doctor.report_migrations),
        devServer: t(keys.dashboard.doctor.report_dev_server),
        applied: t(keys.dashboard.doctor.applied),
        pending: t(keys.dashboard.doctor.pending),
        checkLabels,
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
            <Button variant="outline" size="sm" className="max-lg:min-h-11" onClick={copyReport}>
              {t(keys.dashboard.doctor.copy_report)}
            </Button>
            <Button
              size="sm"
              className="gap-1.5 max-lg:min-h-11"
              onClick={() => router.post(RERUN_URL)}
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              {t(keys.dashboard.doctor.rerun)}
            </Button>
          </>
        }
      >
        <StatsRow stats={props.stats} available={props.checks_available} />

        <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
          <div className="flex min-w-0 flex-col gap-4">
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
          {/* `min-w-0`: a grid item's default `min-width:auto` is its content,
              and the transcript's longest line is wider than a 390px screen —
              it was the one thing making this page scroll sideways. */}
          <div className="flex min-w-0 flex-col gap-4">
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
