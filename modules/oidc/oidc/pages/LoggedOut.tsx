import { Link } from '@inertiajs/react';
import { useT } from '@simple-module-py/i18n';

import messages from '../locales/en.json';

export default function LoggedOut() {
  const { t } = useT();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-2xl font-bold">{t('oidc.logout.title', messages.logout.title)}</h1>
      <p className="text-muted-foreground">{t('oidc.logout.message', messages.logout.message)}</p>
      <Link href="/oidc/login" className="text-primary underline">
        {t('oidc.login.title', messages.login.title)}
      </Link>
    </div>
  );
}
