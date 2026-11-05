import type { DoctorProps } from './types';

/** Section headings, translated by the caller. */
export interface ReportLabels {
  title: string;
  checks: string;
  /** Stands in for the tally when the checks never ran. */
  checksUnavailable: string;
  migrations: string;
  devServer: string;
  applied: string;
  pending: string;
  /** Check label by check id. */
  checkLabels: Record<string, string>;
}

const STATUS_MARK: Record<string, string> = {
  pass: '✓',
  warn: '!',
  fail: '✗',
  unknown: '?',
};

/**
 * The "Copy report" payload: a plain-text snapshot of the whole screen.
 *
 * Meant to be pasted into an issue or a chat thread, so it is deliberately
 * flat text rather than JSON — the person on the other end reads it before
 * anything parses it. Findings are indented under the check that owns them so
 * the shape survives a paste that eats blank lines.
 */
export function buildDoctorReport(props: DoctorProps, labels: ReportLabels): string {
  const { stats } = props;
  // Same reasoning as the stat card: "0/8" in a pasted report would tell the
  // reader every check failed, when in fact none of them ran.
  const tally = props.checks_available
    ? `${stats.checks_passing}/${stats.checks_total}`
    : labels.checksUnavailable;
  const lines: string[] = [
    labels.title,
    `${labels.checks}: ${tally} · ` +
      `modules ${stats.modules_loaded} · pending migrations ${stats.pending_migrations} · ` +
      `python ${stats.python_version}`,
    '',
  ];

  for (const check of props.checks) {
    lines.push(
      `${STATUS_MARK[check.status] ?? '?'} ${labels.checkLabels[check.id] ?? check.id} — ${check.status}`,
    );
    for (const finding of check.findings) {
      lines.push(`    ${finding.code} ${finding.module}: ${finding.message}`);
      if (finding.file) lines.push(`      ${finding.file}`);
      if (finding.suggestion) lines.push(`      → ${finding.suggestion}`);
    }
  }

  lines.push('', labels.migrations);
  for (const row of props.migrations) {
    const module = row.module ? ` [${row.module}]` : '';
    lines.push(
      `    ${row.id}${module} ${row.message} — ${row.applied ? labels.applied : labels.pending}`,
    );
  }

  lines.push('', labels.devServer);
  for (const row of props.dev_server.rows) {
    lines.push(`    ${row.name} ${row.value}`);
  }

  return `${lines.join('\n')}\n`;
}
