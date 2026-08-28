import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@simple-module-py/ui/components/ui/card';
import { BRAND_ACCENT, BRAND_DEFAULT_APP_NAME } from '@simple-module-py/ui/lib/brand';
import type { SharedProps } from '@simple-module-py/ui/types';
import { CheckCircle2, Circle, Database } from 'lucide-react';
import { useState } from 'react';
import { AdministratorForm } from './AdministratorForm';
import { type CheckResult, ConnectionList } from './ConnectionList';

interface SetupStep {
  id: string;
  title: string;
  description: string;
  complete: boolean;
}

interface MigrationState {
  current: string | null;
  head: string | null;
  isCurrent: boolean;
}

interface WizardProps {
  checks: CheckResult[];
  steps: SetupStep[];
  migration: MigrationState;
}

/**
 * First-run setup.
 *
 * Served in place of the app while any required step is incomplete, and
 * unreachable (404) the moment they all pass — which is also what bounds the
 * migration button below, an endpoint that can run Alembic over HTTP.
 */
function Wizard() {
  const { t } = useT();
  const page = usePage<{ props: WizardProps & SharedProps }>().props as unknown as WizardProps &
    SharedProps;
  const { checks, steps, migration, branding } = page;
  const [migrating, setMigrating] = useState(false);
  const [migrationError, setMigrationError] = useState<string | null>(null);

  const appName = branding?.appName ?? BRAND_DEFAULT_APP_NAME;
  const brandInitial = appName.trim().charAt(0).toUpperCase() || 'S';

  async function applyMigrations() {
    setMigrating(true);
    setMigrationError(null);
    try {
      const resp = await fetch('/setup/migrations', {
        method: 'POST',
        headers: { Accept: 'application/json' },
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || resp.statusText);
      }
      window.location.reload();
    } catch (err) {
      setMigrationError((err as Error).message);
      setMigrating(false);
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Head title={t(keys.host.setup.title)} />

      <div className="mx-auto w-full max-w-2xl space-y-6 px-4 py-12">
        {/* No site nav here on purpose. The public shell offers "Log in",
            which during setup points at a sign-in page that no account can
            pass and that the gate redirects straight back here. */}
        <div className="flex items-center gap-2.5">
          {branding?.logoUrl ? (
            <img
              src={branding.logoUrl}
              alt={appName}
              className="h-8 w-8 rounded-lg object-contain"
            />
          ) : (
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-lg ${BRAND_ACCENT} shadow-md shadow-primary-600/30`}
            >
              <span className="font-bold text-white text-sm">{brandInitial}</span>
            </div>
          )}
          <span className="text-[15px] font-bold tracking-tight">{appName}</span>
        </div>

        <header className="space-y-1">
          <h1 className="text-2xl font-semibold">{t(keys.host.setup.title)}</h1>
          <p className="text-muted-foreground">{t(keys.host.setup.subtitle)}</p>
        </header>

        <Card>
          <CardHeader>
            <CardTitle>{t(keys.host.setup.connections.heading)}</CardTitle>
            <CardDescription>{t(keys.host.setup.connections.description)}</CardDescription>
          </CardHeader>
          <CardContent>
            <ConnectionList initial={checks} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t(keys.host.setup.migrations.heading)}</CardTitle>
            <CardDescription>
              {migration.isCurrent
                ? t(keys.host.setup.migrations.current)
                : t(keys.host.setup.migrations.behind)}
            </CardDescription>
          </CardHeader>
          {!migration.isCurrent && (
            <CardContent className="space-y-2">
              <Button type="button" disabled={migrating} onClick={applyMigrations}>
                <Database className="size-4" />
                {migrating
                  ? t(keys.host.setup.migrations.applying)
                  : t(keys.host.setup.migrations.apply)}
              </Button>
              {migrationError && <p className="text-sm text-destructive">{migrationError}</p>}
            </CardContent>
          )}
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t(keys.host.setup.administrator.heading)}</CardTitle>
            <CardDescription>{t(keys.host.setup.administrator.description)}</CardDescription>
          </CardHeader>
          <CardContent>
            <AdministratorForm />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t(keys.host.setup.steps.heading)}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {steps.map((step) => (
                <li key={step.id} className="flex items-start gap-2 text-sm">
                  {step.complete ? (
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary-700" />
                  ) : (
                    <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  )}
                  <span>
                    <span className="font-medium">{step.title}</span>
                    {step.description && (
                      <span className="block text-muted-foreground">{step.description}</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default Wizard;
