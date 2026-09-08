import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'dashboard.doctor.stat_checks_passing': 'Checks passing',
    'dashboard.doctor.stat_checks_total': '/ {count}',
    'dashboard.doctor.stat_checks_unavailable': 'not available',
    'dashboard.doctor.stat_modules_loaded': 'Modules loaded',
    'dashboard.doctor.stat_pending_migrations': 'Pending migrations',
    'dashboard.doctor.stat_python': 'Python',
  },
});

import { buildDoctorReport } from '../dashboard/pages/components/doctor/report';
import { StatsRow } from '../dashboard/pages/components/doctor/StatsRow';
import type { DoctorProps } from '../dashboard/pages/components/doctor/types';

const STATS = {
  checks_passing: 0,
  checks_total: 8,
  modules_loaded: 12,
  pending_migrations: 0,
  python_version: '3.12.4',
};

const PROPS: DoctorProps = {
  checks: [{ id: 'pages', status: 'unknown', command: null, findings: [] }],
  checks_available: false,
  migrations: [{ id: 'a3f1beef', module: 'users', message: 'add invite table', applied: true }],
  migration_commands: { generate: 'make migrations', apply: 'make migrate' },
  dev_server: { running: true, rows: [{ name: 'vite', value: ':5050' }] },
  pages_routed: 26,
  stats: STATS,
};

const LABELS = {
  title: 'Doctor',
  checks: 'Checks',
  checksUnavailable: 'not available (diagnostics run in development only)',
  migrations: 'Migrations',
  devServer: 'Dev server',
  applied: 'applied',
  pending: 'pending',
  checkLabels: { pages: 'Orphan pages' },
};

/** The "Checks passing" card, isolated from its three siblings. */
function checksCard(): HTMLElement {
  const card = screen.getByText('Checks passing').closest('[data-slot="card"]');
  if (!card) throw new Error('Checks passing card not found');
  return card as HTMLElement;
}

describe('StatsRow', () => {
  test('shows the tally when the checks actually ran', () => {
    render(<StatsRow stats={{ ...STATS, checks_passing: 7 }} available={true} />);

    const card = within(checksCard());
    expect(card.getByText('7')).toBeInTheDocument();
    expect(card.getByText('/ 8')).toBeInTheDocument();
    expect(card.queryByText('not available')).not.toBeInTheDocument();
  });

  test('never reports zero passing when the checks never ran', () => {
    // "0 / 8" on a deployment reads as every check failing, which is the
    // opposite of the truth: none of them were run at all.
    render(<StatsRow stats={STATS} available={false} />);

    const card = within(checksCard());
    expect(card.queryByText('0')).not.toBeInTheDocument();
    expect(card.queryByText('/ 8')).not.toBeInTheDocument();
    expect(card.getByText('—')).toBeInTheDocument();
    expect(card.getByText('not available')).toBeInTheDocument();
  });

  test('the other three figures are real either way', () => {
    render(<StatsRow stats={STATS} available={false} />);

    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('3.12.4')).toBeInTheDocument();
  });
});

describe('buildDoctorReport', () => {
  test('says the checks are unavailable rather than writing 0/8', () => {
    const report = buildDoctorReport(PROPS, LABELS);

    expect(report).toContain('Checks: not available (diagnostics run in development only)');
    expect(report).not.toContain('0/8');
  });

  test('writes the tally when the checks did run', () => {
    const report = buildDoctorReport(
      { ...PROPS, checks_available: true, stats: { ...STATS, checks_passing: 7 } },
      LABELS,
    );

    expect(report).toContain('Checks: 7/8');
    expect(report).not.toContain('not available');
  });

  test('carries the migrations and dev-server sections either way', () => {
    const report = buildDoctorReport(PROPS, LABELS);

    expect(report).toContain('a3f1beef [users] add invite table — applied');
    expect(report).toContain('vite :5050');
  });
});
