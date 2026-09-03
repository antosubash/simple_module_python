import { keys, useT } from '@simple-module-py/i18n';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { AlertTriangle, Check, XCircle } from 'lucide-react';
import { useCheckLabels } from './check-copy';
import type { DoctorCheck, DoctorFinding } from './types';

interface Props {
  checks: DoctorCheck[];
  /** False outside development — the card says so instead of showing rows. */
  available: boolean;
  onCopyCommand: (command: string) => void;
}

const TONE = {
  warn: {
    box: 'border-amber-200 bg-amber-50/70',
    title: 'text-amber-700',
    action: 'text-amber-700 hover:text-amber-800',
  },
  fail: {
    box: 'border-red-200 bg-red-50/70',
    title: 'text-red-700',
    action: 'text-red-700 hover:text-red-800',
  },
} as const;

function Finding({ finding }: { finding: DoctorFinding }) {
  return (
    <div className="mt-1 text-[12.5px] text-muted-foreground">
      <code className="font-mono text-[11px]">{finding.code}</code> · {finding.module} —{' '}
      {finding.message}
      {finding.file && (
        <div className="mt-0.5">
          <code className="font-mono text-[11px]">{finding.file}</code>
        </div>
      )}
      {finding.suggestion && <div className="mt-0.5">{finding.suggestion}</div>}
    </div>
  );
}

function PassRow({ label, passLabel }: { label: string; passLabel: string }) {
  return (
    <div className="flex items-center gap-3 text-[13.5px]">
      <Check className="h-3.5 w-3.5 shrink-0 text-primary-700" aria-hidden="true" />
      <span className="min-w-0 flex-1">{label}</span>
      <span className="shrink-0 text-[12.5px] text-muted-foreground">{passLabel}</span>
    </div>
  );
}

function ProblemRow({
  check,
  label,
  fixLabel,
  onCopyCommand,
}: {
  check: DoctorCheck;
  label: string;
  fixLabel: string;
  onCopyCommand: (command: string) => void;
}) {
  const tone = check.status === 'fail' ? TONE.fail : TONE.warn;
  const Icon = check.status === 'fail' ? XCircle : AlertTriangle;
  return (
    <div className={`flex items-start gap-3 rounded-lg border px-3.5 py-3 ${tone.box}`}>
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone.title}`} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className={`text-[13.5px] font-medium ${tone.title}`}>{label}</div>
        {check.findings.map((finding) => (
          <Finding
            // `file` is part of the identity: one module can raise the same
            // code with the same message for two different files, and without
            // it the rows collide on key and React drops a real finding.
            key={`${finding.code}-${finding.module}-${finding.file ?? ''}-${finding.message}`}
            finding={finding}
          />
        ))}
      </div>
      {check.command && (
        <button
          type="button"
          onClick={() => onCopyCommand(check.command as string)}
          className={`shrink-0 text-[12.5px] font-medium max-lg:min-h-11 ${tone.action}`}
        >
          {fixLabel}
        </button>
      )}
    </div>
  );
}

/**
 * The deck's "Static checks" panel.
 *
 * A passing check is one quiet line; only a check with something to say opens
 * into a tinted box. That asymmetry is the point — a healthy install should
 * read as a short list, not a wall of green badges.
 */
export function ChecksCard({ checks, available, onCopyCommand }: Props) {
  const { t } = useT();
  const labels = useCheckLabels();

  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <h2 className="mb-3 text-base font-bold font-[var(--font-display)]">
          {t(keys.dashboard.doctor.static_checks)}
        </h2>
        {available ? (
          <div className="flex flex-col gap-3">
            {checks.map((check) =>
              check.status === 'pass' ? (
                <PassRow
                  key={check.id}
                  label={labels[check.id] ?? check.id}
                  passLabel={t(keys.dashboard.doctor.status_pass)}
                />
              ) : (
                <ProblemRow
                  key={check.id}
                  check={check}
                  label={labels[check.id] ?? check.id}
                  fixLabel={t(keys.dashboard.doctor.fix)}
                  onCopyCommand={onCopyCommand}
                />
              ),
            )}
          </div>
        ) : (
          <div className="rounded-lg border border-border px-4 py-6 text-center">
            <div className="text-sm font-semibold text-foreground">
              {t(keys.dashboard.doctor.checks_unavailable_title)}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {t(keys.dashboard.doctor.checks_unavailable_hint)}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
