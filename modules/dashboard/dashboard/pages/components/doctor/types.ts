/** Doctor page props. Every field is live state — see `dashboard/doctor.py`. */

/** One diagnostic finding, already trimmed to a repo-relative path. */
export interface DoctorFinding {
  level: 'error' | 'warning';
  code: string;
  message: string;
  module: string;
  file: string | null;
  suggestion: string | null;
}

/**
 * A named check, backed by a group of diagnostic codes.
 *
 * `unknown` is what a deployment reports: the checks read the source tree, so
 * they only run in development. A check with no findings there would otherwise
 * be indistinguishable from a check that never ran.
 */
export interface DoctorCheck {
  id: string;
  status: 'pass' | 'warn' | 'fail' | 'unknown';
  /** Copied to the clipboard by the row's "Fix" action. */
  command: string;
  findings: DoctorFinding[];
}

export interface MigrationRow {
  id: string;
  /** Alembic branch label; only a module's first migration carries one. */
  module: string;
  message: string;
  applied: boolean;
}

export interface DevServer {
  running: boolean;
  rows: { name: string; value: string }[];
}

export interface DoctorStats {
  checks_passing: number;
  checks_total: number;
  modules_loaded: number;
  pending_migrations: number;
  python_version: string;
}

export interface DoctorProps {
  checks: DoctorCheck[];
  /** False outside development, where the checks never ran. */
  checks_available: boolean;
  migrations: MigrationRow[];
  migration_commands: { generate: string; apply: string };
  dev_server: DevServer;
  pages_routed: number;
  stats: DoctorStats;
}
