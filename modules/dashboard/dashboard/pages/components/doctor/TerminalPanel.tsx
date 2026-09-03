import { keys, useT } from '@simple-module-py/i18n';
import type { DoctorProps } from './types';

/** The command this screen mirrors. Shown as a prompt line, verbatim. */
const COMMAND = 'make doctor';

/** Enough warnings to establish the shape without turning into a log viewer. */
const MAX_WARNINGS = 4;

type Line = { text: string; tone: 'prompt' | 'plain' | 'warn' | 'ok' };

const TONE_CLASS: Record<Line['tone'], string> = {
  prompt: 'text-slate-400',
  plain: 'text-slate-200',
  warn: 'text-amber-300',
  ok: 'text-emerald-300',
};

/**
 * A transcript of the run the rest of the screen is reporting on.
 *
 * Every line is derived from the same props the cards render, so it can never
 * describe a different run — which is exactly what the fixture version of this
 * panel did.
 */
export function TerminalPanel({ props }: { props: DoctorProps }) {
  const { t } = useT();
  const { stats, checks, checks_available: available } = props;

  const warnings = checks
    .flatMap((check) => check.findings)
    .slice(0, MAX_WARNINGS)
    .map(
      (finding): Line => ({
        tone: 'warn',
        text: t(keys.dashboard.doctor.transcript_warn, {
          message: `${finding.module}: ${finding.message}`,
        }),
      }),
    );

  const lines: Line[] = [
    // i18n-exempt: shell command, shown as typed
    { tone: 'prompt', text: `$ ${COMMAND}` },
    {
      tone: 'plain',
      text: t(keys.dashboard.doctor.transcript_modules, { count: stats.modules_loaded }),
    },
    {
      tone: 'plain',
      text: t(keys.dashboard.doctor.transcript_pages, { count: props.pages_routed }),
    },
    ...(available
      ? [
          ...warnings,
          {
            tone: 'ok' as const,
            text: t(keys.dashboard.doctor.transcript_result, {
              passed: stats.checks_passing,
              total: stats.checks_total,
            }),
          },
        ]
      : [{ tone: 'warn' as const, text: t(keys.dashboard.doctor.transcript_skipped) }]),
  ];

  return (
    <div className="flex min-h-40 flex-col gap-1.5 overflow-hidden rounded-xl bg-slate-900 p-4 font-mono text-[12.5px] leading-[1.75]">
      {lines.map((line, index) => (
        <span
          // A transcript is an ordered list, and two warnings can legitimately
          // carry the same text; position is the identity here.
          // biome-ignore lint/suspicious/noArrayIndexKey: see above
          key={index}
          className={`truncate ${TONE_CLASS[line.tone]}`}
        >
          {line.text}
        </span>
      ))}
    </div>
  );
}
