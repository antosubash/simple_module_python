import { Head } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { Power } from 'lucide-react';

export default function LoggedOut() {
  const { t } = useT();
  return (
    <AuthCardShell>
      <Head title={t(keys.keycloak.logout.title)} />
      <div className="flex flex-col items-center gap-4 text-center">
        <span className="inline-flex h-[52px] w-[52px] items-center justify-center rounded-[14px] bg-secondary text-muted-foreground">
          <Power className="h-[22px] w-[22px]" aria-hidden="true" />
        </span>
        <h1 className="text-[21px] font-bold tracking-tight text-foreground font-[var(--font-display)]">
          {t(keys.keycloak.logout.title)}
        </h1>
        <p className="max-w-[380px] text-sm leading-relaxed text-muted-foreground">
          {t(keys.keycloak.logout.message)}
        </p>
        <div className="flex flex-wrap justify-center gap-2.5">
          <Button asChild className="max-lg:min-h-11">
            <a href="/keycloak/login">{t(keys.keycloak.logout.sign_in_again)}</a>
          </Button>
          <Button variant="outline" asChild className="max-lg:min-h-11">
            <a href="/">{t(keys.keycloak.logout.back_to_site)}</a>
          </Button>
        </div>
      </div>
    </AuthCardShell>
  );
}
