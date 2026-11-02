import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';

export default function LoggedOut() {
  const { t } = useT();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-2xl font-bold">{t(keys.oidc.logout.title)}</h1>
      <p className="text-muted-foreground">{t(keys.oidc.logout.message)}</p>
      <Link href="/oidc/login" className="text-primary underline">
        {t(keys.oidc.logout.sign_in_again)}
      </Link>
    </div>
  );
}
