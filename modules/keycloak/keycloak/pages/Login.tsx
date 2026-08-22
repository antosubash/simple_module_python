import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { useEffect } from 'react';

export default function Login() {
  const { t } = useT();
  useEffect(() => {
    router.get('/api/keycloak/auth/login');
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted-foreground">{t(keys.keycloak.login.redirecting)}</p>
    </div>
  );
}
