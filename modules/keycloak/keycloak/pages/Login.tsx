import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { LogIn } from 'lucide-react';
import { useEffect } from 'react';

const START_LOGIN_URL = '/api/keycloak/auth/login';

interface Props {
  /** `https://sso.example.com/realms/acme`, or "" when the realm is unset. */
  realm_url: string;
}

export default function Login() {
  const { realm_url } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  useEffect(() => {
    // A full-page assign, not `router.get`: the endpoint answers with a 302 to
    // the Keycloak realm, and Inertia rejects a cross-origin response to an
    // XHR it expects a page payload from.
    window.location.assign(START_LOGIN_URL);
  }, []);

  return (
    <AuthCardShell>
      <Head title={t(keys.keycloak.login.title)} />
      <div className="flex flex-col items-center gap-4 text-center">
        <span className="inline-flex h-[52px] w-[52px] items-center justify-center rounded-[14px] bg-primary-600/10 text-primary-700">
          <LogIn className="h-[22px] w-[22px]" aria-hidden="true" />
        </span>
        <h1 className="text-[21px] font-bold tracking-tight text-foreground font-display">
          {t(keys.keycloak.login.redirecting)}
        </h1>
        <p className="max-w-[380px] text-sm leading-relaxed text-muted-foreground">
          {realm_url ? (
            <>
              {t(keys.keycloak.login.body_prefix)}{' '}
              <code className="font-mono text-[13px] text-foreground">{realm_url}</code>
              {t(keys.keycloak.login.body_suffix)}
            </>
          ) : (
            t(keys.keycloak.login.body_generic)
          )}
        </p>
        {/* Indeterminate on purpose: the wait is a browser redirect to
            another origin, whose progress this page cannot observe. A bar
            frozen at some percentage claims knowledge it does not have. */}
        <div
          role="progressbar"
          aria-label={t(keys.keycloak.login.progress_label)}
          className="h-[5px] w-[220px] overflow-hidden rounded-full bg-secondary"
        >
          {/* No aria-valuenow: ARIA reads a progressbar without one as
              indeterminate, which is exactly the claim being made. */}
          <div className="h-full w-full animate-pulse rounded-full bg-primary-600" />
        </div>
        <a
          href={START_LOGIN_URL}
          className="text-[13px] font-medium text-primary-700 hover:text-primary-800"
        >
          {t(keys.keycloak.login.manual)}
        </a>
      </div>
    </AuthCardShell>
  );
}
