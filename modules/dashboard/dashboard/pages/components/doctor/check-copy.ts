import { keys, useT } from '@simple-module-py/i18n';

/**
 * Check id → its human label, in one place.
 *
 * Both the card and the copied report name these checks, and a mapping written
 * twice is a mapping that drifts: a new check added to `dashboard/doctor.py`
 * would silently render as its raw id in whichever copy was forgotten.
 */
export function useCheckLabels(): Record<string, string> {
  const { t } = useT();
  return {
    pages: t(keys.dashboard.doctor.checks.pages),
    metadata: t(keys.dashboard.doctor.checks.metadata),
    coupling: t(keys.dashboard.doctor.checks.coupling),
    migrations: t(keys.dashboard.doctor.checks.migrations),
    locales: t(keys.dashboard.doctor.checks.locales),
    inertia: t(keys.dashboard.doctor.checks.inertia),
    auth_provider: t(keys.dashboard.doctor.checks.auth_provider),
    styling: t(keys.dashboard.doctor.checks.styling),
  };
}
