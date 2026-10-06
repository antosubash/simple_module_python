import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@simple-module-py/ui/components/ui/card';
import { BRAND_ACCENT, BRAND_DEFAULT_APP_NAME } from '@simple-module-py/ui/lib/brand';
import type { SharedProps } from '@simple-module-py/ui/types';
import { CheckCircle2, Circle } from 'lucide-react';
import { type CheckResult, ConnectionList } from '../components/ConnectionList';
import { type StepAction, StepForm } from '../components/StepForm';

interface SetupStep {
  id: string;
  title: string;
  description: string;
  complete: boolean;
  /** Present only while the step is pending and its module offers a form. */
  action: StepAction | null;
}

interface WizardProps {
  checks: CheckResult[];
  steps: SetupStep[];
  csrfToken: string;
}

/**
 * First-run setup, shipped by `simple_module_hosting`.
 *
 * Served in place of the app while any required step is incomplete, and
 * unreachable (404) the moment they all pass. Each pending step whose module
 * registered an action gets its own form; the rest are listed so the operator
 * can see what is left and complete it out of band.
 */
function Wizard() {
  const { t } = useT();
  const page = usePage<{ props: WizardProps & SharedProps }>().props as unknown as WizardProps &
    SharedProps;
  const { checks, steps, csrfToken, branding } = page;

  const appName = branding?.appName ?? BRAND_DEFAULT_APP_NAME;
  const brandInitial = appName.trim().charAt(0).toUpperCase() || 'S';

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Head title={t(keys.hosting.setup.title)} />

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
          <h1 className="text-2xl font-semibold">{t(keys.hosting.setup.title)}</h1>
          <p className="text-muted-foreground">{t(keys.hosting.setup.subtitle)}</p>
        </header>

        <Card>
          <CardHeader>
            <CardTitle>{t(keys.hosting.setup.connections.heading)}</CardTitle>
            <CardDescription>{t(keys.hosting.setup.connections.description)}</CardDescription>
          </CardHeader>
          <CardContent>
            <ConnectionList initial={checks} csrfToken={csrfToken} />
          </CardContent>
        </Card>

        {steps.map((step) =>
          step.action ? (
            <Card key={step.id}>
              <CardHeader>
                <CardTitle>{step.title}</CardTitle>
                {step.description && <CardDescription>{step.description}</CardDescription>}
              </CardHeader>
              <CardContent>
                <StepForm stepId={step.id} action={step.action} csrfToken={csrfToken} />
              </CardContent>
            </Card>
          ) : null,
        )}

        <Card>
          <CardHeader>
            <CardTitle>{t(keys.hosting.setup.steps.heading)}</CardTitle>
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
