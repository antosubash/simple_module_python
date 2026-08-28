import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';

export default function LoggedOut() {
  const { t } = useT();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-2xl font-bold">{t(keys.keycloak.logout.title)}</h1>
      <p className="text-muted-foreground">{t(keys.keycloak.logout.message)}</p>
      <Link href="/keycloak/login" className="text-primary underline">
        {t(keys.keycloak.logout.sign_in_again)}
      </Link>
    </div>
  );
}
