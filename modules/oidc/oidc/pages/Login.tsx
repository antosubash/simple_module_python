import { keys, useT } from '@simple-module-py/i18n';
import { useEffect } from 'react';

const START_LOGIN_URL = '/api/oidc/auth/login';

export default function Login() {
  const { t } = useT();
  useEffect(() => {
    window.location.assign(START_LOGIN_URL);
  }, []);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <p className="text-muted-foreground">{t(keys.oidc.login.redirecting)}</p>
      <a href={START_LOGIN_URL} className="text-primary underline">
        {t(keys.oidc.login.manual)}
      </a>
    </div>
  );
}
